"""Fine Print API — live read-only search over the enriched NZ Gazette notices."""
import asyncio
import json
import queue
import threading

from contextlib import asynccontextmanager

import anyio
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app import config as cfg
from app import ratelimit
from app import stats as stats_store
from app.agent import loop as agent_loop
from app.agent.schemas import AskRequest, AskResponse
from app.search import engine, pipeline
from app.search.schemas import CorpusStats, Notice, SearchRequest, SearchResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cap sync-endpoint worker threads per uvicorn worker; --limit-concurrency is the 503 valve
    above this queue."""
    try:
        anyio.to_thread.current_default_thread_limiter().total_tokens = cfg.API_THREADPOOL
    except Exception:
        pass   # tuning only — the default of 40 is fine
    yield


app = FastAPI(
    title="Fine Print API",
    lifespan=lifespan,
    docs_url="/docs" if cfg.ENABLE_DOCS else None,
    redoc_url="/redoc" if cfg.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if cfg.ENABLE_DOCS else None,
)

# Defaults to the local Vite dev server; set CORS_ORIGINS to the real domain(s) in production.
app.add_middleware(CORSMiddleware, allow_origins=cfg.CORS_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])

# Applied to the paid routes only. Named once to keep the decorators readable.
_LIMITED = [Depends(ratelimit.enforce_rate_limits)]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats", response_model=CorpusStats)
def stats():
    """Read from Redis, where the nightly updater publishes it. Unmetered — no DB, no LLM."""
    found = stats_store.corpus_stats()
    if not found:
        raise HTTPException(status_code=503, detail="Stats are not available yet.")
    return found


@app.get("/notices/{notice_id}", response_model=Notice)
def notice(notice_id: str):
    """Gives a result its own address, so it survives a reload, a share and the Back button."""
    found = engine.get_notice(notice_id)
    if not found:
        raise HTTPException(status_code=404, detail="No notice with that id.")
    return found


@app.post("/search", response_model=SearchResponse, dependencies=_LIMITED)
def search(request: SearchRequest):
    """Keyword-shaped queries hit full-text; sentences are LLM-parsed then matched by embedding."""
    try:
        return pipeline.run_search(request.q, request.filters, request.limit)
    except RuntimeError as error:            # e.g. semantic route with no embed key configured
        raise HTTPException(status_code=503, detail=str(error))


@app.post("/ask", response_model=AskResponse, dependencies=_LIMITED)
def ask(request: AskRequest):
    """Runs the research agent, returning its narration, the report, and the notices it read."""
    steps: list[str] = []
    sources: list[dict] = []
    seen_source_ids: set[str] = set()

    def record_step(text: str):
        cleaned = (text or "").strip()
        if cleaned:
            steps.append(cleaned)

    def record_source(notice: dict):
        if notice["id"] not in seen_source_ids:
            seen_source_ids.add(notice["id"])
            sources.append(notice)

    ratelimit.acquire_ask_slot()             # 503 immediately if this worker is at capacity
    try:
        answer = agent_loop.run_agent(request.q, on_step=record_step, on_source=record_source)
    except RuntimeError as error:            # e.g. missing DeepSeek key / embed config
        raise HTTPException(status_code=503, detail=str(error))
    finally:
        ratelimit.release_ask_slot()
    return AskResponse(steps=steps, answer=answer, sources=sources)


_STREAM_DONE = object()      # sentinel the agent thread puts on the queue when it has finished


@app.post("/ask/stream", dependencies=_LIMITED)
async def ask_stream(request: AskRequest):
    """Same research as /ask, but each stage line is pushed as it happens rather than in one batch
    at the end. SSE: {"type":"step"|"source"|"answer"|"error", ...}, one per `data:` line."""
    ratelimit.acquire_ask_slot()             # 503 before we start work if the worker is at capacity
    events: queue.Queue = queue.Queue()
    seen_source_ids: set[str] = set()

    def emit_step(text: str):
        cleaned = (text or "").strip()
        if cleaned:
            events.put({"type": "step", "text": cleaned})

    def emit_source(notice: dict):
        if notice["id"] not in seen_source_ids:
            seen_source_ids.add(notice["id"])
            events.put({"type": "source", "notice": notice})

    def run_agent_into_queue():
        """run_agent blocks, so it gets its own thread and posts events as they happen."""
        try:
            answer = agent_loop.run_agent(request.q, on_step=emit_step, on_source=emit_source)
            events.put({"type": "answer", "text": answer})
        except Exception as error:
            events.put({"type": "error", "message": str(error)})
        finally:
            events.put(_STREAM_DONE)
            ratelimit.release_ask_slot()     # free the slot when the run finishes

    threading.Thread(target=run_agent_into_queue, daemon=True).start()

    async def event_stream():
        loop = asyncio.get_running_loop()
        while True:
            event = await loop.run_in_executor(None, events.get)   # don't block the event loop
            if event is _STREAM_DONE:
                break
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

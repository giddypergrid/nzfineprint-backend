"""The agent loop: question -> DeepSeek plans -> calls tools -> synthesizes. Reasoning ON, unlike
the query parser, because this needs real multi-step planning. MAX_ROUNDS caps the cost.

Tool results feed back each round, so the model can retry with new args and stops when it has enough.
"""
import json
import os
import re

from openai import OpenAI

from app import config as cfg
from app.agent import tools
from app.agent.prompt import SYSTEM_PROMPT
from app.agent.tool_specs import TOOL_SPECS

MAX_ROUNDS = int(os.getenv("AGENT_MAX_ROUNDS", "6"))
AGENT_MODEL = os.getenv("AGENT_MODEL", cfg.DEEPSEEK_MODEL)

# Keeps the loop from knowing any tool's internals.
_DISPATCH = {
    "search_notices": tools.search_notices,
    "get_notice": tools.get_notice,
    "get_company_history": tools.get_company_history,
    "find_related_parties": tools.find_related_parties,
}


def run_agent(question: str, on_step=None, on_source=None) -> str:
    """Drive the loop to a final answer. on_step receives each narration line for the UI; on_source
    receives every notice read in full, which are the citations behind the answer."""
    client = OpenAI(api_key=cfg.DEEPSEEK_API_KEY, base_url=cfg.DEEPSEEK_BASE_URL)
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question}]

    for _ in range(MAX_ROUNDS):
        response = client.chat.completions.create(
            model=AGENT_MODEL, tools=TOOL_SPECS, max_tokens=1500,
            extra_body={"thinking": {"type": "enabled"}},
            messages=messages,
        )
        msg = response.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:           # no more tools -> this is the answer
            content = msg.content or ""
            if _looks_like_leaked_tool_call(content):
                # DeepSeek sometimes writes a tool call as prose, which would become the "answer".
                messages.append({"role": "user", "content":
                    "Your last reply contained tool-call syntax instead of a real lookup. Make the "
                    "lookup properly, or give your final answer now as plain prose with no tool or "
                    "function syntax."})
                continue
            return _clean_answer(content)

        for call in msg.tool_calls:      # run every tool the model asked for
            arguments = _parse_arguments(call.function.arguments)
            narration = arguments.pop("narration", None)   # the model's own stage line for the UI
            if narration and on_step:
                on_step(narration)

            result = _run_tool(call.function.name, arguments)
            _record_source_if_read(call.function.name, result, on_source)
            messages.append({"role": "tool", "tool_call_id": call.id,
                             "content": json.dumps(result, default=str)})

    # Hit the round cap — ask for a final answer from what's gathered, no more tools.
    messages.append({"role": "user", "content":
                     "Wrap up now with the best answer you can from what you've found so far."})
    final = client.chat.completions.create(model=AGENT_MODEL, max_tokens=1500,
                                           extra_body={"thinking": {"type": "enabled"}},
                                           messages=messages)
    return _clean_answer(final.choices[0].message.content or "")


# Tells of a leaked tool call. The UI renders plain text, so none of this can reach it.
_MARKUP_MARKERS = ("DSML", "invoke name=", "<tool_call", "｜tool", "▁tool")


def _looks_like_leaked_tool_call(text: str) -> bool:
    return any(marker in text for marker in _MARKUP_MARKERS)


def _clean_answer(text: str) -> str:
    """Safety net: drop leaked tool-call markup and the markdown the prompt already forbids, which
    the UI would otherwise show raw."""
    if not text:
        return ""
    for marker in _MARKUP_MARKERS:            # keep only the prose before any leaked markup
        cut = text.find(marker)
        if cut != -1:
            text = text[:cut]
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)      # ATX headings
    text = re.sub(r"(?m)^\s*[-*_]{3,}\s*$", "", text)      # horizontal rules
    text = re.sub(r"`([^`]*)`", r"\1", text)               # inline code
    return text.strip()


def _record_source_if_read(tool_name: str, result: object, on_source) -> None:
    """A get_notice call means the agent read a notice in full, which makes it a cited source."""
    if on_source is None or tool_name != "get_notice":
        return
    if isinstance(result, dict) and result.get("id") and not result.get("error"):
        on_source(result)


def _parse_arguments(raw_args: str) -> dict:
    """Malformed JSON becomes {}, which the tool rejects with an error the model can recover from."""
    try:
        return json.loads(raw_args or "{}")
    except json.JSONDecodeError:
        return {}


def _run_tool(name: str, arguments: dict) -> object:
    """Unknown tool, bad arguments and DB errors all come back as an error dict rather than crashing
    the loop, so the model can read the failure and try something else."""
    fn = _DISPATCH.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return fn(**arguments)
    except Exception as error:
        return {"error": str(error)}

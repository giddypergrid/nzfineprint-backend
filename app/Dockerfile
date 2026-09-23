# Live API image — FastAPI served by uvicorn. Runs as the `app` package (absolute imports),
# so the code is copied under /srv/app and uvicorn is pointed at app.main:app from /srv.
FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Non-root: the API only reads the DB and writes request logs. uid 1000 must own the
# host's Prep/data/logs bind mount, or request logging fails silently.
RUN useradd --create-home --uid 1000 app
COPY --chown=app:app . ./app
USER app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

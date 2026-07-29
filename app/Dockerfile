# Live API image — FastAPI served by uvicorn. Runs as the `app` package (absolute imports),
# so the code is copied under /srv/app and uvicorn is pointed at app.main:app from /srv.
FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

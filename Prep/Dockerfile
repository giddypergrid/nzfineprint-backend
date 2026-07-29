# Offline job image — pull / enrich / load / vectorize. Also runs the scheduled daily update.
#   one-off : docker compose run --rm prep python -m pipeline.pull
#   manual  : docker compose run --rm prep sh run_update.sh
#   schedule: the `updater` service runs `supercronic /app/crontab`
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# supercronic: a cron built for containers (proper logging, passes env to jobs). Used by the
# updater service. Strip CRLF in case the shell/crontab were checked out on Windows (LF-only or
# /bin/sh and cron both choke on \r).
ADD https://github.com/aptible/supercronic/releases/download/v0.2.33/supercronic-linux-amd64 /usr/local/bin/supercronic
RUN chmod +x /usr/local/bin/supercronic \
 && sed -i 's/\r$//' /app/crontab /app/run_update.sh

CMD ["python", "-m", "pipeline.pull"]     # default job; override on the run line

# Offline job image — pull / enrich / load / vectorize. Also runs the scheduled daily update.
#   one-off : docker compose run --rm prep python -m pipeline.pull
#   manual  : docker compose run --rm prep sh run_update.sh
#   schedule: the `updater` service runs `supercronic /app/crontab`
FROM python:3.12-slim
WORKDIR /app

# pg_dump for the nightly backup. It must be >= the server (Postgres 17) or it refuses with a
# version mismatch, and Debian's own package trails — hence PGDG rather than the default one.
#
# The suite is read from the base image (`trixie-pgdg`, `bookworm-pgdg`, ...) instead of being
# named literally: python:3.12-slim moved from bookworm to trixie, and a hardcoded bookworm suite
# then failed to resolve against a trixie base — PGDG's bookworm libpq5 wants libldap-2.5-0, which
# trixie does not carry (it ships 2.6). Deriving it means the next base bump cannot repeat that.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
http://apt.postgresql.org/pub/repos/apt $(. /etc/os-release && echo $VERSION_CODENAME)-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-17 \
 && apt-get purge -y gnupg && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# supercronic: a cron built for containers (proper logging, passes env to jobs). Used by the
# updater service. Strip CRLF in case the shell/crontab were checked out on Windows (LF-only or
# /bin/sh and cron both choke on \r).
ADD https://github.com/aptible/supercronic/releases/download/v0.2.33/supercronic-linux-amd64 /usr/local/bin/supercronic
RUN chmod +x /usr/local/bin/supercronic \
 && sed -i 's/\r$//' /app/crontab /app/run_update.sh /app/run_backup.sh

CMD ["python", "-m", "pipeline.pull"]     # default job; override on the run line

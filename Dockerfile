# Narcos on-prem app image (D83). Built by CI (linux/amd64), run on the
# client's Windows box via Docker Desktop. Contains code + dependencies +
# collected static only — NEVER secrets. Every NARCOS_* secret arrives at
# runtime from .env, so this image is safe to hold in a private registry.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=narcos.settings

# tini: proper PID 1 (signal handling + zombie reaping) for a long-lived server.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first so the layer caches across code-only changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Collect static at build time (whitenoise serves from STATIC_ROOT). No DB or
# real secret is touched — a throwaway key just satisfies Django's startup.
RUN NARCOS_SECRET_KEY=build-time-only python manage.py collectstatic --noinput

RUN chmod +x docker-entrypoint.sh

EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--", "/app/docker-entrypoint.sh"]
CMD ["waitress-serve", "--listen=0.0.0.0:8080", "narcos.wsgi:application"]

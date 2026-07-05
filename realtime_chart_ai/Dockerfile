# realtime_chart_ai — standalone deployment image.
# Self-contained on purpose: build context is this directory, not the repo
# root, matching the "isolated sibling project" philosophy the whole feature
# was built around. The React frontend (frontend_src/) is NOT built here —
# its output is already committed at frontend/ (see frontend_src/package.json's
# "deploy" script), so this image stays pure-Python.

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8800

# Render (and most PaaS hosts) inject $PORT and require the app to bind to
# it; run_server.py reads RTC_PORT (settings.py), not $PORT directly, so map
# one into the other at container start rather than changing app code for a
# host-specific convention. Falls back to 8800 for local `docker run`.
CMD ["sh", "-c", "RTC_PORT=${PORT:-8800} python run_server.py"]

# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    WORKERS=2 \
    DB_PATH=/app/data/dpsynth.db

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application codebase
COPY app/ ./app/
COPY static/ ./static/
COPY run.py .

# Create data directory and non-root user
RUN mkdir -p /app/data && \
    useradd -u 1000 -m -s /bin/bash dpsynth && \
    chown -R dpsynth:dpsynth /app

USER dpsynth

VOLUME ["/app/data"]
EXPOSE 8000

# Built-in Container Health Check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Production Entrypoint
CMD ["python", "run.py"]

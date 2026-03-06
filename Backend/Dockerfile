# syntax=docker/dockerfile:1
FROM python:3.10-slim AS base

WORKDIR /app
ARG APP_ENV=production
ENV APP_ENV=${APP_ENV}

# System dependencies for OpenCV headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgl1-mesa-glx curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (server-only layer — cached separately)
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt \
    && pip install --no-cache-dir prometheus-client prometheus-fastapi-instrumentator \
    && pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir ultralytics

# Copy application code
COPY API/         ./API/
COPY Inference/   ./Inference/

# Ensure YOLO model directory exists (model mounted at runtime via volume or copied in CI)
RUN mkdir -p Inference/Models/yolo

# Create non-root user
RUN useradd -m -u 1001 walksense
RUN chown -R walksense:walksense /app
USER walksense

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["python", "-m", "uvicorn", "API.server:app", \
     "--host", "0.0.0.0", "--port", "8080", \
     "--workers", "1", "--log-level", "warning"]

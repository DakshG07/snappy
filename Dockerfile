FROM node:22-bookworm-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATABASE_PATH=/data/scanny.db \
    DOCUMENT_STORAGE_PATH=/data/documents \
    PADDLE_CACHE_PATH=/data/paddle \
    FRONTEND_DIST_PATH=/app/frontend/build \
    SECURE_COOKIES=true

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 libgl1 libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements-ocr.txt /app/backend/
RUN python -m pip install --no-cache-dir -r /app/backend/requirements.txt \
    && python -m pip install --no-cache-dir -r /app/backend/requirements-ocr.txt

COPY backend/ /app/backend/
COPY --from=frontend-build /app/frontend/build /app/frontend/build
COPY docker-entrypoint.sh /app/docker-entrypoint.sh

RUN chmod +x /app/docker-entrypoint.sh \
    && mkdir -p /data/documents /data/paddle

EXPOSE 8000
CMD ["/app/docker-entrypoint.sh"]

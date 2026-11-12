FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEBHOOK_INBOX_DB_PATH=/data/webhook_inbox.db \
    WEBHOOK_INBOX_BASE_URL=http://localhost:8000

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 inbox \
    && mkdir -p /data \
    && chown -R inbox:inbox /data /app

USER inbox
VOLUME ["/data"]
EXPOSE 8000

CMD ["uvicorn", "--factory", "webhook_inbox.app:create_app", "--host", "0.0.0.0", "--port", "8000"]

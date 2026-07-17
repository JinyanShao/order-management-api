FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml alembic.ini ./
COPY src ./src
COPY alembic ./alembic
RUN pip install --no-cache-dir . \
    && groupadd --system order-api \
    && useradd --system --gid order-api --home-dir /nonexistent --shell /usr/sbin/nologin order-api \
    && chown -R order-api:order-api /app
USER order-api
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn order_api.main:app --host 0.0.0.0 --port 8000 --no-access-log"]

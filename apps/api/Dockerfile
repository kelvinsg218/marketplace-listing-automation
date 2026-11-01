FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY . .
# Dependencies come from pyproject.toml (single source of truth); dev extras bring pytest for the RLS tests.
RUN pip install --no-cache-dir ".[dev]"
RUN useradd --create-home app && mkdir -p /data && chown app /data
USER app
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn mla_api.asgi:app --host 0.0.0.0 --port 8000"]

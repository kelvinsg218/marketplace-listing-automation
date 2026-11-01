FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir "fastapi==0.115.14" "uvicorn[standard]==0.54.0" "SQLAlchemy==2.0.55" "alembic==1.20.1" \
    "psycopg[binary]==3.2.13" "pydantic-settings==2.16.2" "argon2-cffi==25.1.0" "email-validator>=2.2" \
    "pytest>=9" "httpx==0.28.1"
COPY . .
RUN useradd --create-home app && mkdir -p /data && chown app /data
USER app
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn mla_api.asgi:app --host 0.0.0.0 --port 8000"]

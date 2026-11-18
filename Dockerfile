FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "exec uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml ./
COPY uv.lock ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
RUN uv export --locked --no-dev --format requirements-txt --no-emit-project \
    > /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && pip install --no-cache-dir --no-deps .

USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "toolplanner.main:app", "--host", "0.0.0.0", "--port", "8000"]

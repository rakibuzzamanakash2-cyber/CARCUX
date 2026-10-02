FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install .
COPY alembic.ini ./
COPY migrations ./migrations

# Run as an unprivileged user. It owns only the media directory.
RUN useradd --create-home --uid 10001 carcux \
    && mkdir -p /app/media && chown carcux /app/media
USER carcux

EXPOSE 8000
# Apply database migrations, then serve.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

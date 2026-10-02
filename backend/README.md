# CARCUX backend

FastAPI service for field reports, events, evidence and the audit log.

## Run locally (Python)

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

Open http://localhost:8000/api/v1/health and http://localhost:8000/docs.

## Run the full stack (Docker)

From the repository root:

```bash
docker compose -f deployment/docker-compose.yml up --build
```

This starts PostgreSQL + PostGIS (port 5432), Redis (6379) and the API (8000).

## Checks

```bash
ruff check .
ruff format --check .
pytest
```

CI runs the same commands on every push and pull request.

## Layout

```
backend/
├── app/
│   ├── main.py          # application factory
│   ├── core/config.py   # settings (env prefix CARCUX_)
│   └── api/             # routers
└── tests/
```

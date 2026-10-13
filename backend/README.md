# Backend (FastAPI)

Python API for the car rental platform. See the root [README.md](../README.md)
for the project overview and stage tracker.

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # runtime + test/lint tools (requirements.txt = runtime only)
cp .env.example .env                  # local settings; never commit .env
```

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

- Health check: http://localhost:8000/api/v1/health
- Interactive docs (non-production only): http://localhost:8000/docs (Swagger UI), http://localhost:8000/redoc
- OpenAPI schema: http://localhost:8000/api/v1/openapi.json

When `APP_ENV=production`, `/docs`, `/redoc`, and the OpenAPI schema are disabled.

## Test and lint

```bash
pytest                 # automated tests
ruff check .           # lint
ruff format --check .  # formatting
```

## Configuration

Settings come from environment variables, or from `backend/.env` when running from `backend/`.
See [.env.example](.env.example).

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `development` | `development`, `test`, `staging`, or `production` |
| `APP_NAME` | `Car Rental API` | Shown in API docs and the health response |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `CORS_ORIGINS` | *(none)* | Comma-separated allowed browser origins |

## Structure

```
app/
├── main.py            # create_app() factory: middleware, error handlers, routers
├── core/
│   ├── config.py      # Settings (pydantic-settings) and dependencies
│   ├── errors.py      # AppError base class and the error-envelope exception handlers
│   └── logging.py
├── api/
│   ├── router.py      # Mounts route modules under /api/v1
│   └── routes/        # One module per resource (health.py)
└── schemas/           # Pydantic request and response models
tests/                 # Pytest suite (one app per test, isolated settings)
```

Business logic goes in `app/services/` and database access in
`app/models/`/`app/repositories/` from Stage 04 onward. Route handlers stay thin.

## Error format

Every error response uses the same envelope:

```json
{"error": {"code": "validation_error", "message": "Request validation failed.",
           "details": [{"location": ["body", "seats"], "message": "...", "type": "int_parsing"}]}}
```

Validation errors never echo the submitted values. Unexpected errors return a
generic 500 message and are logged on the server with the full traceback.
Services raise subclasses of `AppError` (with `status_code` and `code`) for
expected business errors.

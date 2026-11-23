# AI Career Companion

An AI-powered career platform for students looking for internships: profile and resume intelligence, internship matching, skill-gap analysis, tailored applications, interview preparation, application tracking, and two separate assistants (a **Career Assistant** and a **Product Assistant**).

Runs entirely on **localhost**: React + Vite frontend, FastAPI backend, and Supabase PostgreSQL (+ pgvector) as the database. No local PostgreSQL install is needed.

> Status: **Phase 1 complete**: foundation, database migrations and authentication. See [`docs/01_DESIGN_BLUEPRINT.md`](docs/01_DESIGN_BLUEPRINT.md) for the full plan.

## Prerequisites

- Python **3.11**
- Node.js **18+** (developed on 24)
- A Supabase project (free tier) and a Google Gemini API key

## 1. Configure environment

```powershell
Copy-Item backend\.env.example backend\.env
```

Fill in `backend\.env`:

| Variable | Where it comes from |
|---|---|
| `DATABASE_URL` | Supabase → **Connect** → URI → **Session pooler**. Change the prefix to `postgresql+psycopg://` and insert your DB password (URL-encode `@ # /`). Don't use "Direct connection": it is IPv6-only. |
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `GEMINI_API_KEY` | Google AI Studio → Get API key |

`.env` is git-ignored. Never commit it.

## 2. Backend

```powershell
cd backend
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\alembic upgrade head          # creates tables in Supabase, enables pgvector + RLS
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs · Health: http://localhost:8000/api/health

## 3. Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api/*` to the backend on port 8000.

## Tests

```powershell
cd backend
.venv\Scripts\python -m pytest                      # all tests
.venv\Scripts\python -m pytest -m "not integration" # skip tests that hit Supabase
```

API tests use an in-memory SQLite database. Tests marked `integration` are read-only checks against Supabase: connectivity, migrations at head, RLS on every table, and pgvector enabled.

## Project layout

```
backend/
  app/
    main.py            FastAPI app, CORS, request-id logging, error handlers
    config.py          settings from backend/.env
    db.py              SQLAlchemy engine/session (Supabase session pooler)
    security.py        bcrypt + JWT (access/refresh)
    models/  schemas/  services/  routers/
  alembic/             database migrations
  tests/
frontend/
  src/
    api/client.js      axios client: auth header, single-flight token refresh
    auth/              AuthContext (login/register/logout/session restore)
    pages/ components/
docs/                  design blueprint, (later) product knowledge document & diagrams
```

## Security notes

- Passwords: bcrypt. Login errors never reveal whether the email exists.
- Tokens: 30-minute access JWT + 7-day refresh JWT. Refresh tokens are **rotated** on every use and stored only as SHA-256 hashes. Reuse of a revoked refresh token revokes all of that user's sessions.
- Supabase: every table has **row-level security enabled** with no policies, so Supabase's public REST API cannot read app data. The backend connects as the table owner and is unaffected. **Every new migration that creates a table must enable RLS on it**; `tests/test_integration_db.py` fails otherwise.
- Validation errors never echo submitted values. Unhandled errors return a generic 500 with a request id; details go to the server log only.

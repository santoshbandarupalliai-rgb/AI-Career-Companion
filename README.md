# AI Career Companion

An AI-powered career platform for students looking for internships: profile and resume intelligence, internship matching, skill-gap analysis, tailored applications, interview preparation, application tracking, and two separate assistants (a **Career Assistant** and a **Product Assistant**).

Runs entirely on **localhost**: React + Vite frontend, FastAPI backend, and Supabase PostgreSQL (+ pgvector) as the database. No local PostgreSQL install is needed.

> Status: **Phase 7 complete**: all nine modules. Authentication, student profile, resume parsing and skill review, the internship knowledge base (sample postings, paste-a-JD, semantic search), explainable job matching and skill-gap analysis, tailored resumes and cover letters with a fact guard, interview practice, the application tracker, the Career Assistant (tool-using agent), and the Product Assistant (RAG chat with memory, sessions and citations). See [`docs/01_DESIGN_BLUEPRINT.md`](docs/01_DESIGN_BLUEPRINT.md) for the full plan.

## How resume parsing works

1. Upload a PDF or DOCX (max 5 MB). The file type is checked by its content, not just its name. Text is extracted with **PyMuPDF** (multi-column aware) or **python-docx** (paragraphs, tables, headers). Scanned/image-only files are rejected with a clear message.
2. **Gemini** (`gemini-2.5-flash`, JSON-schema output, temperature 0) structures the text, with instructions to copy only what is written.
3. A **deterministic grounding check** removes any skill, project technology or contact detail that does not appear in the resume text, and lists what it removed as warnings.
4. If Gemini is unavailable, a heuristic parser (regex + a skill catalog) produces a partial result; the student can re-run extraction later.
5. Skills are normalized through an alias catalog (`JS` → JavaScript, `k8s` → Kubernetes; "Java" never matches "JavaScript") and stored as **extracted**. Only the student can mark them **verified** or **rejected**, and re-extraction never overrides those decisions.

## How the internship knowledge base works

1. **Sample data**: 20 postings from *fictional* companies, stored with `source='sample'` and shown with a "Sample" badge. Seed them once with `python -m app.seed` (idempotent).
2. **Add from a job description**: paste the text; Gemini extracts the fields and required/preferred skills, a grounding check drops anything not in the pasted text, and you review and edit the draft before anything is saved. Postings you add are private to you.
3. **Semantic search**: each posting is chunked and embedded locally with `fastembed` (`BAAI/bge-small-en-v1.5`, 384-dim; the ~130 MB model downloads on first use) into pgvector, searched by cosine similarity (HNSW index). Keyword filters (work mode, location, skill, source) combine with it.

## How tailoring and interview prep work

- **Tailoring**: the AI may only rephrase what is already in your profile and resume. Employers, titles and dates are copied from your resume (the model refers to entries by index), the resume skills list contains only *verified* skills, and a deterministic **fact guard** flags invented numbers, unverified skills, unknown names and bullets that do not resemble their source. You get a draft, edit it, and approve it; saving re-runs the checks and asks you to confirm anything still flagged. Export to .docx.
- **Interview prep**: questions generated from the role or posting plus your verified skills and real projects (no canned bank), scored against a fixed 0-10 rubric (relevance 4, structure 3, depth 3) with feedback. Sessions are saved. Scores are AI feedback, not a grade.

## How matching and skill gap work

Scores are **deterministic**: fixed rules over your *verified* skills, so the same profile always gives the same number, and every point is explained.

`score = 50% required skills + 15% preferred skills + 20% profile-to-posting similarity + 10% education fit + 5% experience fit`

- Only verified skills count; unverified resume skills are shown as a hint.
- If a posting or your profile does not give enough information for a factor, that factor is marked *not applicable* and its weight is shared across the others. Nothing is guessed.
- Graduation-year and minimum-CGPA requirements are shown as met / not met / unknown when the posting states them, but do not change the score.
- **Skill gap** ranks missing skills (critical = required, secondary = preferred) by how many postings ask for them, for one internship or a target role.
- The AI is used only for the optional "Explain in words" and "Create learning plan" buttons, on top of numbers it cannot change.

## How the application tracker and Career Assistant work

- **Tracker**: track a knowledge-base posting with one click (company and role are copied from it) or add an external one. Statuses: saved, applied, online assessment, interview, offer, rejected, withdrawn. Every change is logged with an optional note; deadlines show days left.
- **Career Assistant**: a LangGraph agent that calls the app's own tools (profile, internship search, match ranking and scoring, skill gap, interview questions, tracker) for up to 4 steps per message, then answers from the results. Scores and gaps come from the same deterministic rules as the other pages. It **cannot change data**: adding or updating an application shows up as a proposal under the answer, and nothing happens until you press Confirm. The model only sees short item codes, never database ids, and the server checks every code.

## How the Product Assistant works

The Product Assistant answers questions about this product from one source, [`docs/02_PRODUCT_KNOWLEDGE_DOCUMENT.md`](docs/02_PRODUCT_KNOWLEDGE_DOCUMENT.md). It is a LangGraph pipeline:

1. **load history**: fetch this session's messages by `(user_id, session_id, assistant_type)`; other users' and other sessions' chats are never visible.
2. **condense**: rewrite a follow-up like "why did we use it?" into a standalone question using the history.
3. **retrieve**: embed the question and fetch the top 5 document sections from pgvector (cosine). If none is similar enough, the assistant says it is not in the documentation, without calling the model.
4. **generate**: Gemini answers using only those sections and marks the ones it used as `[n]`.
5. **persist**: store the question, answer and citations; long chats are summarised so older context is kept.

Each answer lists its sources and can be rated 👍/👎. Chats are listed per user and can be deleted. Run `python -m app.seed` after editing the document to re-index it.

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

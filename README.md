# AI Career Companion

An AI-powered career platform for students looking for internships: profile and resume intelligence, internship matching, skill-gap analysis, tailored applications, interview preparation, application tracking, and two separate assistants (a **Career Assistant** and a **Product Assistant**).

Runs entirely on **localhost**: React + Vite frontend, FastAPI backend, and Supabase PostgreSQL (+ pgvector) as the database. No local PostgreSQL install is needed.

> **Status: complete and tested.** All nine modules, the status dashboard and both assistants are built and working: authentication, student profile, resume parsing and skill review, the internship knowledge base (sample postings, paste-a-JD, semantic search), explainable job matching and skill-gap analysis, tailored resumes and cover letters with a fact guard, interview practice, the application tracker, the Career Assistant (tool-using agent) and the Product Assistant (RAG chat with memory, sessions and citations). See [`docs/01_DESIGN_BLUEPRINT.md`](docs/01_DESIGN_BLUEPRINT.md) for the design and build plan.

## Documentation

| File | What it is |
|---|---|
| [`docs/01_DESIGN_BLUEPRINT.md`](docs/01_DESIGN_BLUEPRINT.md) | Requirements, architecture decisions and the build plan |
| [`docs/02_PRODUCT_KNOWLEDGE_DOCUMENT.md`](docs/02_PRODUCT_KNOWLEDGE_DOCUMENT.md) | Product Knowledge Document (the Product Assistant's only source). Exports: [`docs/exports/`](docs/exports/) (.docx and .pdf) |
| [`docs/03_DEMO_SCRIPT.md`](docs/03_DEMO_SCRIPT.md) | Step-by-step demo through every module and both assistants |
| [`docs/04_DIAGRAMS.md`](docs/04_DIAGRAMS.md) | Mermaid diagrams: architecture, RAG pipeline, both assistant graphs, database schema |
| [`docs/05_AGILE_PLAN.md`](docs/05_AGILE_PLAN.md) | Agile plan: product vision, milestones, epics and user stories, backlog status and retrospective |
| [`docs/deliverables/`](docs/deliverables/) | Agile Project Documentation (PDF and DOCX, with screenshots) and the 10-slide project presentation (PPTX) |

## Dashboard

After sign-in the dashboard shows real status from your own data: profile completeness (6 key fields), whether a resume is active, verified vs awaiting-review skills, applications per status, upcoming deadlines, and one suggested next step. It is read-only and uses no AI.

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
- **Interview Prep Agent**: a chat agent (`/api/chat/interview`, `assistant_type='interview'`) that uses the extracted resume data, verified skills, the profile and the matching engine's results as context. It recommends roles and internships, names the strongest skills, writes role-specific technical and HR questions with answer guidance, a preparation roadmap and a learning path, and answers questions about PDF/DOCX files uploaded to the chat (chunked, embedded and retrieved with pgvector, corpus `prep_doc`). Same guardrails and PII masking as the other assistants.
- **Interview prep (mock interview)**: a chat in which the interviewer asks one question at a time, generated from the role or posting plus your verified skills and real projects (no canned bank). Each answer is scored against a fixed 0-10 rubric (relevance 4, structure 3, depth 3) with feedback, and a diagnostic report (level, score per question type, recurring strengths and improvements) is calculated from the saved scores. An answer that only tries to instruct the evaluator is not sent to the AI and scores 0. Sessions are saved. Scores are AI feedback, not a grade.
- **Several resumes**: keep up to 10 resumes, name them (for example "Backend resume"), and pick which one tailoring and interview practice use; the active one is the default.

## How matching and skill gap work

Scores are **deterministic**: fixed rules over your *verified* skills, so the same profile always gives the same number, and every point is explained.

`score = 50% required skills + 15% preferred skills + 20% profile-to-posting similarity + 10% education fit + 5% experience fit`

- Only verified skills count; unverified resume skills are shown as a hint.
- If a posting or your profile does not give enough information for a factor, that factor is marked *not applicable* and its weight is shared across the others. Nothing is guessed.
- Graduation-year and minimum-CGPA requirements are shown as met / not met / unknown when the posting states them, but do not change the score.
- **Skill gap** ranks missing skills (critical = required, secondary = preferred) by how many postings ask for them, for one internship or a target role.
- The AI is used only for the optional "Explain in words" and "Create learning plan" buttons, on top of numbers it cannot change.

## How the application tracker and Career Assistant work

- **Apply (demo)**: every internship card has an Apply button. It records the application as *Applied* in the tracker (resume choice and a note are optional; a Saved application is moved forward, a duplicate is refused). The postings are fictional, so nothing is sent to any company; the button is labelled as a demo.
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
| `GROQ_API_KEY` (optional) | console.groq.com → API Keys. Fallback when Gemini is rate-limited or down. `GROQ_MODEL` (default `openai/gpt-oss-120b`) and `LLM_PROVIDERS` (default `gemini,groq`, the order tried) are optional |

| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` (optional) | An SMTP account for verification emails, for example Gmail with an app password (`smtp.gmail.com`, port 587). `SMTP_STARTTLS` (default true) and `SMTP_SSL` (for port 465) are optional. For Gmail, turn on 2-Step Verification and create an **App Password** (myaccount.google.com/apppasswords); put its 16 characters in `SMTP_PASSWORD` without spaces. **Without these settings no email is sent** (a login user without a password counts as not configured): the verification link is written to the backend log instead, which is enough for development. |
| `APP_BASE_URL` (optional) | Base of the link in verification emails; defaults to `FRONTEND_ORIGIN`. |
| `REQUIRE_EMAIL_VERIFICATION` (optional, default false) | When true, an account must verify its email before it can use anything except `/api/auth/me`, verification and resending. |
| `PII_REDACTION` (optional, default true) | Masks sensitive identifiers in every prompt sent to an AI service. |

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

## Scripts

Run from the repo root (they use the backend virtual environment):

```powershell
cd backend; .venv\Scripts\python -m app.seed                      # index sample internships + product document
backend\.venv\Scripts\python backend\scripts\export_pkd.py         # product document -> docs/exports/*.docx and *.pdf
backend\.venv\Scripts\python backend\scripts\make_sample_resume.py # fictional demo resume PDF
backend\.venv\Scripts\python backend\scripts\delete_e2e_users.py   # remove *-e2e@example.com demo accounts
```

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
    llm/               the only LLM adapter (Gemini, with Groq as fallback)
    rag/               chunker, local embeddings, pgvector retriever
    seed/              fictional sample internships
  alembic/             database migrations
  scripts/             export, demo-resume and cleanup helpers
  tests/
frontend/
  src/
    api/client.js      axios client: auth header, single-flight token refresh
    auth/              AuthContext (login/register/logout/session restore)
    pages/ components/
docs/                  design blueprint, product knowledge document (+ exports), demo script, diagrams
```

## Security notes

- Passwords: bcrypt. Login errors never reveal whether the email exists.
- Tokens: 30-minute access JWT + 7-day refresh JWT. Refresh tokens are **rotated** on every use and stored only as SHA-256 hashes. Reuse of a revoked refresh token revokes all of that user's sessions.
- Supabase: every table has **row-level security enabled** with no policies, so Supabase's public REST API cannot read app data. The backend connects as the table owner and is unaffected. **Every new migration that creates a table must enable RLS on it**; `tests/test_integration_db.py` fails otherwise.
- Validation errors never echo submitted values. Unhandled errors return a generic 500 with a request id; details go to the server log only.
- Logs pass through a redacting formatter that strips SQL parameters, email addresses and tokens, tracebacks included. Resume and job-description text is not logged.
- Every query on user-owned data is filtered by the signed-in user's id; the Career Assistant cannot write data without a button click.
- **Email verification**: after registering, a single-use link (24 hours, stored only as a hash) confirms the address; resending is limited to one email per minute. Accounts created before this existed were marked verified by the migration.
- **PII redaction**: Aadhaar-style ids, PAN, card numbers (Luhn-checked), labelled bank account numbers, IFSC codes, passport numbers, SSNs and labelled dates of birth are masked in every prompt sent to an AI provider. In resumes, the email address and phone number are replaced by placeholders while the AI reads the text and restored afterwards; contact details typed into chats and interview answers are masked. It is pattern based (a safety net, not a guarantee) and the chat history still shows what the user typed.
- **Assistant guardrails**: each assistant has one area. A pre-check answers greetings and refuses prompt-injection attempts without calling the AI; the Career Assistant must classify every message as in or out of scope and an out-of-scope message gets a fixed refusal (no tool runs); the Product Assistant answers only from retrieved documentation sections. Refusal texts are fixed strings.

## Known limitations

- **LLM fallback and privacy**: if `GROQ_API_KEY` is set, a request that Gemini rejects (rate limit, outage, bad output) is retried on Groq, which then receives the same prompt, including resume text. Leave the key empty to keep all text with Gemini.
- **Gemini free tier**: the LLM-backed features (resume parsing, JD extraction, explanations, learning plans, tailoring, interview questions and scoring, both assistants) can answer with a rate-limit or "high demand" message. The app then shows the error and stores nothing; resume parsing falls back to a heuristic parser. Deterministic features (matching, skill gap, tracker, dashboard) do not need it.
- **Testing**: automated tests use fakes for the AI services; all features were also tested manually end to end against the live services, including the Groq fallback. AI output quality can still vary between runs.
- Sample internships are fictional demo data; there is no live job feed.
- Scanned (image-only) resumes are rejected; there is no OCR.
- Tailored documents export to .docx only (no PDF export or CV templates).
- Answers are not streamed; the assistants reply when complete.
- Runs on localhost only; there is no deployment configuration, email verification or password reset.
- The semantic thresholds (`SEM_LOW/SEM_HIGH`, `MIN_SCORE`, `ROLE_MIN_SIMILARITY`) were tuned on the sample data and the current embedding model; re-measure if either changes.

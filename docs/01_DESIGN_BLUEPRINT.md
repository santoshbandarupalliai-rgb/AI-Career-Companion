# AI Career Companion: Requirements, Design and Build Plan

This document records the requirements the project had to meet, the design decisions that follow from them, and the order in which the system was built. The implemented schema and flows are in `04_DIAGRAMS.md`; user-facing behaviour is in `02_PRODUCT_KNOWLEDGE_DOCUMENT.md`.

---

## 1. Goals and design principles

The product helps a student go from a resume to a set of suitable internship applications. Everything is built around a few principles:

1. **Never invent information about the student.** A new account starts empty. Profile fields, skills, qualifications and eligibility are shown only if the student entered them or the resume states them. Sample internships are labelled "Sample" and use fictional companies.
2. **Extracted skills are suggestions; verified skills are facts.** A skill found in a resume stays "extracted" until the student verifies it. Only verified skills are used for matching, skill gaps and generated documents.
3. **Scores are computed, not asserted.** Matching and skill-gap results come from deterministic rules with a visible breakdown. The language model may rephrase or recommend, but it never decides a number.
4. **Generated text is checked against the source.** Tailored resumes and cover letters pass a fact guard, and the student approves before anything is saved.
5. **Strict per-user isolation.** Every user-owned query is filtered by user id; chat history is also filtered by session and assistant type.
6. **Fail visibly and safely.** If an AI call fails, the user sees a clear message and nothing is stored. Deterministic features keep working without AI.

---

## 2. Requirements

### 2.1 Functional modules

| # | Module | Summary |
|---|---|---|
| 1 | Student profile and resumes | Academic profile, resume upload (PDF/DOCX), versions |
| 2 | Resume parsing and skill review | Structured extraction, verify / reject / add skills |
| 3 | Internship knowledge base | Browse, semantic search, add from a pasted job description |
| 4 | Job matching | Explainable 0-100 compatibility score |
| 5 | Skill gap | Ranked missing skills and a learning plan |
| 6 | Resume and cover letter tailoring | Role-specific drafts with a fact guard |
| 7 | Interview preparation | Generated questions, rubric feedback, saved sessions |
| 8 | Application tracker | Statuses, history, deadlines |
| 9 | Career Assistant | Chat assistant that uses the student's data through tools |
| + | Product Assistant | RAG chatbot over the Product Knowledge Document |

### 2.2 Product Assistant requirements

1. **Product Knowledge Document** (DOCX and PDF) with: Overview, Features (name, purpose, how it works, how to use, output), How to Use, Architecture (with diagram) and Tech Stack (with the reason for each choice).
2. **RAG pipeline**: load the document, extract text, chunk, embed, store in a vector database, embed the query, retrieve, call the LLM with the context, answer.
3. **Conversation memory** that resolves references such as "why did we use *it*?" from earlier turns.
4. **Conversation storage** in a database: user, session, query, response, timestamp.
5. **Memory flow**: fetch history by (user, session), retrieve, combine system prompt, history, context and query, call the LLM, return and persist.
6. **Multi-user, multi-session isolation**: history is always filtered by both ids.
7. **Deliverables**: source code, README (run steps, dependencies, environment variables, database setup), architecture diagram, RAG flow diagram, database schema, and a demo of RAG, memory and multiple users and sessions.

Extras implemented: chat-history UI, multiple sessions, source citations, LangGraph workflow, authentication, 👍/👎 feedback and long-history summarisation. Streaming answers were left out.

Vector store choice: **pgvector on Supabase Postgres** satisfies the vector-database requirement and keeps a single datastore; the justification is in the Product Knowledge Document.

---

## 3. Architecture

```
React + Vite (localhost:5173)  ──/api proxy──▶  FastAPI (localhost:8000)
                                                 │
     ┌───────────────────────────────────────────┼─────────────────────────────────┐
     │ routers/  (thin: validation, auth, HTTP)  │                                 │
     │ services/ (deterministic Python: parsing, scoring, CRUD, chunking)          │
     │ agents/   (LangGraph graphs + single-purpose LLM chains)                    │
     │ llm/      (provider adapter: structured JSON and text generation)           │
     └───────────────────────────────────────────┼─────────────────────────────────┘
                                                 ▼
                           Supabase PostgreSQL (+ pgvector)  ←  SQLAlchemy 2.0 + Alembic
                           Local disk: uploads/ (git-ignored)
```

### 3.1 Key technology decisions

| Decision | Choice | Why |
|---|---|---|
| DB connection | Supabase **session pooler**, driver `psycopg` v3 | The direct host is IPv6-only on the free tier; the pooler works on IPv4 networks and supports prepared statements. |
| Migrations | **Alembic** | The schema changed across phases; `create_all` cannot alter tables. |
| Auth | Own JWT (access + rotating refresh tokens), Supabase used only as Postgres | One identity system; no extra row-level-security work for the MVP. |
| LLM | **Google Gemini** (`gemini-2.5-flash`) behind a provider adapter, with an optional **Groq** fallback | Free tier, native JSON-schema output. The adapter is the only module that knows the providers, retries with backoff and falls back when a provider is rate-limited or returns bad output. |
| Embeddings | **fastembed** with `BAAI/bge-small-en-v1.5` (384-dim), local | No API cost or rate limits, small ONNX runtime, deterministic. |
| Vector store | **pgvector** `vector(384)` with an HNSW cosine index | One datastore; SQL filters (`corpus`, `user_id`) apply in the same query. |
| Orchestration | **LangGraph**, only for the two assistants | Everything else is a plain function call. |
| Resume extraction | **PyMuPDF** (PDF) and **python-docx** (DOCX, including tables) | Handles multi-column layouts and tables without external services. |
| Frontend | React 18, Vite, React Router, axios | Small and conventional. |
| Logging | stdlib `logging` with a request-id middleware and a redacting formatter | Structured, safe logs. |

### 3.2 Components and failure handling

| Component | Kind | Responsibility | Failure handling |
|---|---|---|---|
| Resume extractor | LLM chain | Structure raw resume text into a schema | Validate, retry once, fall back to a heuristic parser and mark the result "partial". Absent fields stay empty. |
| Matching | Deterministic scorer + LLM explainer | Score each internship against the verified profile | If the LLM fails, the score and factor table are still returned. The score never depends on the LLM. |
| Skill gap | Deterministic diff + LLM recommender | Missing skills ranked by importance, plus a learning plan | If the LLM fails, gaps are returned without a plan. No canned courses or links. |
| Tailoring | LLM chain with fact guard | Tailored resume bullets and cover letter | Employers, titles and dates are copied from the resume; skills are filtered to verified ones; unsupported claims are flagged; the student approves before saving. |
| Interview prep | LLM chain | Generate role- and resume-specific questions; score answers | Schema validation and retry; nothing is stored if the call fails. |
| **Career Assistant** | LangGraph with a tool loop | Understand the request and call tools | Tool errors become observations; at most four tool steps; changes are only proposed and need a click to confirm. |
| **Product Assistant** | LangGraph (linear) | Answer questions from the knowledge document | If retrieval similarity is below the threshold: "not covered in the documentation". Answers carry citations. |

Product Assistant graph: `load_history` → `condense` (rewrites "why did we use it?" into a standalone question) → `retrieve` (pgvector, top 5, product corpus) → `generate` → `persist` → `summarize` when the history is long.

Career Assistant graph: `load_context` → `agent` ⇄ `tools` → `persist` → `summarize`.

**Separation of the assistants:** different routers (`/api/chat/career/...`, `/api/chat/product/...`), graphs, prompts and frontend pages, and `chat_sessions.assistant_type` is enforced on every query. The Product Assistant has no access to user data; the Career Assistant never reads the product corpus.

### 3.3 Matching score

```
overall = 0.50·required_skill_coverage
        + 0.15·preferred_skill_coverage
        + 0.20·semantic_similarity(profile_text, internship_text)   # pgvector cosine, rescaled to 0..1
        + 0.10·education_fit
        + 0.05·experience_fit
```

- Skills are normalised through an alias catalogue (`"js"` → `javascript`) and matched as whole tokens, never as substrings.
- **Only verified skills count.**
- The response lists every factor's value, weight and contribution. A factor without enough information is marked not applicable and its weight is redistributed; nothing is clamped.
- Eligibility (graduation year, minimum CGPA) is shown as met / not met / unknown only when the posting states it, and never changes the score.

### 3.4 Data model

The implemented schema is drawn in `04_DIAGRAMS.md` (section 5). Every table has Row Level Security enabled, and all user-owned queries go through services that require a user id. Chat history is always fetched with the user, session and assistant type.

### 3.5 Repository layout

```
ai-career-companion/
├─ docs/        design blueprint, product knowledge document, demo script, diagrams, exports
├─ backend/     app/{models, schemas, routers, services, llm, rag, seed}, alembic/, tests/, scripts/
├─ frontend/    Vite React app
├─ .gitignore   README.md
```

---

## 4. Build plan

The system was built in phases. A phase is finished only when its check passes, it has automated tests, it has been verified in the browser, and it is committed.

| Phase | Scope | Done when |
|---|---|---|
| 1 | Foundation: repo, config, logging, Supabase connection, Alembic, JWT auth, React shell | Register and sign in work end to end |
| 2 | Profile, resume upload and parsing, skill review | A real resume is parsed and its skills can be verified or rejected |
| 3 | Internship knowledge base: sample seed, paste-a-JD, embeddings, semantic search | Search returns ranked internships; every posting shows its source |
| 4 | Product Knowledge Document and Product Assistant (RAG, memory, sessions, citations) | RAG answers, follow-up resolution, and multi-user, multi-session isolation work |
| 5 | Deterministic matching and skill gap | The match page shows a score breakdown; the gap page shows ranked gaps |
| 6 | Resume and cover-letter tailoring with fact guard; interview prep | Generated documents flag unsupported claims; sessions are saved |
| 7 | Application tracker and Career Assistant | "Find internships that fit me and add the top one to my tracker" works across tools |
| 8 | Dashboard, error states, log redaction, hardening | Tests are green; no unhandled 500s in the demo path |
| 9 | Documentation, diagrams, demo script, exports | All deliverables present |

Features cut for scope: voice input, conversation export, streaming answers, PDF export of tailored resumes and CV templates.

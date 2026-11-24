# AI Career Companion: Diagrams

All diagrams are Mermaid and were written from the code (not copied from the blueprint). They render on GitHub and in most Markdown viewers.
Source files are named in each section so they can be checked.

## 1. System architecture

```mermaid
flowchart TB
    subgraph Browser["Browser (React 18 + Vite)"]
        UI["Header (Product Assistant, user menu), side menu,<br/>floating Career Assistant button.<br/>Pages: Dashboard, Profile, Resume, Internships,<br/>Matching, Skill Gap, Customize, Interview,<br/>Applications, Career Assistant, Product Assistant"]
        AX["api/client.js<br/>axios + single-flight token refresh"]
        UI --> AX
    end

    subgraph API["FastAPI backend (backend/app)"]
        MW["Middleware: request id, access log,<br/>redacting log formatter, 500 handler"]
        R["routers/*<br/>HTTP + validation + JWT (deps.get_current_user)"]
        S["services/*<br/>business logic, every query filtered by user_id"]
        PURE["match_engine.py, fact_guard.py<br/>pure functions: no DB, no LLM"]
        LLMA["llm/client.py<br/>the only LLM adapter<br/>(providers tried in LLM_PROVIDERS order)"]
        RAG["rag/*<br/>chunker, embeddings, retriever"]
        MW --> R --> S
        S --> PURE
        S --> LLMA
        S --> RAG
    end

    subgraph Ext["External / local"]
        GEM["Google Gemini<br/>gemini-2.5-flash (primary)"]
        GRQ["Groq (optional fallback)<br/>openai/gpt-oss-120b"]
        EMB["fastembed (local)<br/>BAAI/bge-small-en-v1.5, 384 dims"]
        DB[("Supabase PostgreSQL<br/>session pooler, pgvector 0.8, RLS on")]
        FS["backend/uploads/&lt;user_id&gt;/<br/>resume files"]
    end

    AX -- "/api (Vite proxy to 127.0.0.1:8000)" --> MW
    LLMA --> GEM
    LLMA -. "on rate limit, outage<br/>or bad output" .-> GRQ
    RAG --> EMB
    S --> DB
    RAG --> DB
    S --> FS
```

Notes: LLM and embedding calls happen outside database transactions (the service rolls back first and persists afterwards). Only verified skills reach the matching and gap code. If Gemini fails, the same prompt goes to Groq (when `GROQ_API_KEY` is set) and the answer is validated against the same schema; if every provider fails, the user sees an error and nothing is stored.

## 2. RAG pipeline

Both the internship search and the Product Assistant use the same code in `app/rag/`, with different `corpus` values (`internship`, `product`).

### 2.1 Indexing

```mermaid
flowchart LR
    A1["Product Knowledge Document<br/>docs/02_PRODUCT_KNOWLEDGE_DOCUMENT.md"] --> P["product_kb.parse_sections<br/>one section per ## / ### heading"]
    A2["Internship posting<br/>(sample seed, pasted JD, or user)"] --> T["posting text<br/>title, company, skills, description"]
    P --> H{"content_hash<br/>changed?"}
    T --> H
    H -- "no" --> SKIP["skip (no re-embedding)"]
    H -- "yes" --> C["chunker.chunk_text<br/>max 1200 chars, 150 overlap"]
    C --> E["embeddings.embed_documents<br/>bge-small, 384-dim, local"]
    E --> U["retriever.upsert_document<br/>rag_documents + rag_chunks"]
    U --> DB[("Postgres + pgvector<br/>HNSW cosine index")]
```

Run `python -m app.seed` to (re)index the sample internships and the product document. Embedding happens before the database transaction opens.

### 2.2 Answering (Product Assistant)

```mermaid
flowchart LR
    Q["User question"] --> CQ["condense<br/>(LLM) rewrite follow-up<br/>as a standalone question"]
    CQ --> EQ["embed_query<br/>(query prefix, local model)"]
    EQ --> S["retriever.search<br/>corpus=product, top 5,<br/>best chunk per section"]
    S --> F{"score >= 0.55?"}
    F -- "none pass" --> NF["fixed 'not covered' reply<br/>no LLM call, no citations"]
    F -- "some pass" --> G["generate (LLM, structured)<br/>covered, answer with [n] markers"]
    G --> CIT["citations = only the sections marked [n]"]
    NF --> OUT["stored reply"]
    CIT --> OUT
```

## 3. Product Assistant graph

`services/product_assistant.py` (LangGraph, strictly linear). `assistant_type='product'`.

```mermaid
flowchart LR
    START([START]) --> LH["load_history<br/>ownership check, recent turns,<br/>summary; ensure KB indexed"]
    LH --> CO["condense<br/>(LLM, skipped if no history)"]
    CO --> RT["retrieve<br/>pgvector search, MIN_SCORE 0.55"]
    RT --> GE["generate<br/>(LLM) or not-found reply"]
    GE --> PE["persist<br/>chat_repo.add_turn<br/>with citations"]
    PE --> SU["summarize<br/>fold old messages when over 20<br/>(best effort)"]
    SU --> END([END])
```

If generation fails nothing is stored and the router answers 503 with the adapter's user-safe message.

## 4. Career Assistant graph

`services/career_assistant.py` (LangGraph with a tool loop). `assistant_type='career'`. Separate router (`/api/chat/career`), prompts and tools from the Product Assistant; it never reads the product corpus.

```mermaid
flowchart TB
    START([START]) --> LC["load_context<br/>history, summary, item codes<br/>from earlier turns"]
    LC --> AG["agent<br/>one structured LLM call = AgentStep<br/>(call a tool, or reply)"]
    AG -- "tool chosen and fewer than 4 tool steps" --> TL["tools<br/>run the tool via existing services,<br/>result becomes an observation,<br/>db.rollback() afterwards"]
    TL --> AG
    AG -- "reply, or 4 steps used (forced final reply)" --> PE["persist<br/>reply + tool trace + pending actions"]
    PE --> SU["summarize<br/>best effort"]
    SU --> END([END])
```

Tools (all read from services, same rules as the pages): `get_profile`, `search_internships`, `rank_matches`, `score_match`, `skill_gap`, `interview_questions`, `list_applications`, plus the two write **proposals** `propose_track` and `propose_status`.

### Confirm-to-write

The model never changes data. A proposal is stored as a pending action on the reply; only a click executes it, using the stored parameters.

```mermaid
sequenceDiagram
    participant S as Student
    participant UI as Career Assistant page
    participant A as Agent graph
    participant DB as Database

    S->>UI: "Add the top one to my tracker"
    UI->>A: POST /sessions/{id}/messages
    A->>A: tools: rank_matches, then propose_track (I1)
    A->>DB: store reply with action state=pending
    A-->>UI: answer + [Confirm] [Cancel]
    Note over A,DB: Nothing has changed in the tracker yet
    S->>UI: Confirm
    UI->>DB: POST /messages/{id}/actions/{action_id} decision=confirm
    DB->>DB: career_actions.resolve: lock the message, check state=pending,<br/>run application_service with STORED params
    DB-->>UI: state=done (or failed / cancelled)
    Note over UI,DB: A second confirm answers 409
```

Item codes: the model only ever sees `I<n>` (internship) and `A<n>` (application). The server maps codes to ids; an unknown code is an error observation.

## 5. Database schema (ER)

Generated from the SQLAlchemy models (`app/models`). Every table has Row Level Security enabled; `tests/test_integration_db.py` fails if one does not. `rag_chunks.embedding` is `vector(384)` on Postgres.

```mermaid
erDiagram
    users ||--o| student_profiles : has
    users ||--o{ resumes : uploads
    users ||--o{ student_skills : has
    users ||--o{ refresh_tokens : holds
    users ||--o{ email_tokens : "verifies with"
    users ||--o{ applications : tracks
    users ||--o{ application_events : owns
    users ||--o{ chat_sessions : owns
    users ||--o{ chat_messages : owns
    users ||--o{ message_feedback : gives
    users ||--o{ generated_documents : saves
    users ||--o{ interview_sessions : practises
    users ||--o{ interview_items : owns
    users |o--o{ internships : "creates (source=user)"

    resumes ||--o| resume_extractions : "latest parse"
    resumes |o--o{ student_skills : "evidence from"
    resumes |o--o{ applications : "used in"

    skills ||--o{ student_skills : "status: extracted / verified / rejected"
    skills ||--o{ internship_skills : "required / preferred"
    internships ||--o{ internship_skills : lists
    internships |o--o{ applications : "linked (NULL = external)"
    internships |o--o{ generated_documents : "tailored for"
    internships |o--o{ interview_sessions : "practised for"

    applications ||--o{ application_events : "status history"

    chat_sessions ||--o{ chat_messages : contains
    chat_messages ||--o{ message_feedback : rated
    interview_sessions ||--o{ interview_items : questions
    rag_documents ||--o{ rag_chunks : "split into"

    users {
        uuid id PK
        string full_name
        string email
        string hashed_password
        bool is_active
        datetime email_verified_at
    }
    email_tokens {
        uuid user_id FK
        string purpose
        string token_hash
        datetime expires_at
        datetime used_at
    }
    student_profiles {
        uuid user_id FK
        string college
        string degree
        string branch
        float cgpa
        int graduation_year
        string target_role
    }
    resumes {
        uuid id PK
        uuid user_id FK
        string original_filename
        string label
        text raw_text
        bool is_active
        string extraction_status
    }
    resume_extractions {
        uuid resume_id FK
        json data
        string method
    }
    skills {
        uuid id PK
        string canonical
        string name
        string category
    }
    student_skills {
        uuid user_id FK
        uuid skill_id FK
        string status
        string source
        uuid resume_id FK
    }
    internships {
        uuid id PK
        string title
        string company
        text description
        string source
        string seed_key
        uuid created_by FK
    }
    internship_skills {
        uuid internship_id FK
        uuid skill_id FK
        string importance
    }
    applications {
        uuid id PK
        uuid user_id FK
        uuid internship_id FK
        string company
        string role
        string status
        date deadline
    }
    application_events {
        uuid application_id FK
        string from_status
        string to_status
        string note
    }
    chat_sessions {
        uuid id PK
        uuid user_id FK
        string assistant_type
        text summary
        int summarized_count
    }
    chat_messages {
        uuid id PK
        uuid session_id FK
        int seq
        string role
        text content
        json citations
        json tool_calls
    }
    message_feedback {
        uuid message_id FK
        uuid user_id FK
        int rating
    }
    generated_documents {
        uuid id PK
        uuid user_id FK
        string kind
        json content
        json flagged
    }
    interview_sessions {
        uuid id PK
        uuid user_id FK
        string role
        uuid internship_id FK
    }
    interview_items {
        uuid session_id FK
        text question
        string category
        int score
        json feedback
    }
    rag_documents {
        uuid id PK
        string corpus
        string source_key
        string content_hash
    }
    rag_chunks {
        uuid document_id FK
        string corpus
        int chunk_index
        text content
        vector embedding
    }
    refresh_tokens {
        uuid user_id FK
        string token_hash
        bool revoked
    }
```

`chat_sessions.assistant_type` (`product` or `career`) keeps the two assistants' chats apart; `services/chat_repo.py` is the only code that reads or writes chat rows and always filters by user and assistant type.

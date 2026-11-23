# AI Career Companion: Product Knowledge Document

This document describes the AI Career Companion product. It is the only source the Product Assistant uses to answer questions about the product. Each feature is marked **Available** (works today) or **Planned** (designed but not built yet).

## 1. Overview

### 1.1 What the product is

AI Career Companion is a web application that helps students find and apply for internships. A student builds a profile, uploads a resume, confirms the skills found in it, browses an internship knowledge base, and (in later releases) gets explainable match scores, skill-gap plans, tailored resumes and cover letters, interview practice, an application tracker and a chat-based Career Assistant.

### 1.2 Who it is for

It is built for students and recent graduates looking for internships, especially those who want guidance that is based on their real profile rather than generic advice.

### 1.3 Guiding principles

- **Nothing is invented.** A new profile starts empty. The product never makes up qualifications, internships, skills or eligibility.
- **Extracted is not verified.** Skills read from a resume are "extracted" until the student confirms them. Only "verified" skills will count in matching and skill-gap analysis.
- **AI output is checked.** After the AI reads a document, a deterministic check removes anything that does not actually appear in the source text.
- **Sample data is labelled.** Demo internships come from fictional companies and carry a "Sample" badge.
- **Two separate assistants.** The Product Assistant (answers questions about the product from this document) and the Career Assistant (planned; helps with the student's own career using their profile) are different features with different data access.

### 1.4 Current release

The current release includes: sign-up and sign-in, the student profile, resume upload and parsing, skill review, the internship knowledge base with semantic search, and the Product Assistant. Matching, skill gap, resume and cover-letter tailoring, interview preparation, the application tracker and the Career Assistant are planned and show a "coming soon" page.

## 2. Features

### 2.1 Account and sign-in (Available)

**Purpose:** Keep each student's data private to them.

**How it works:** A student registers with a name, email and a password of at least 8 characters containing a letter and a number. Passwords are stored only as bcrypt hashes. After sign-in the app receives a short-lived access token (30 minutes) and a refresh token (7 days). The app renews the access token automatically, and only a genuine "not authenticated" answer signs the user out, so a network hiccup does not log anyone out.

**How to use:** Open the app, choose "Create one" on the sign-in page, fill in the form, then sign in.

**Output:** A signed-in session and access to the student's own data only.

### 2.2 Student profile (Available)

**Purpose:** Hold the student's academic and career details in one place.

**How it works:** The profile has fields such as college, degree, branch, CGPA, graduation year, target role, location, bio and links (LinkedIn, GitHub, portfolio). It starts empty. Values are validated, for example CGPA must be within a sensible range and links must be valid.

**How to use:** Open "Profile & Resumes" and fill in the form, then save.

**Output:** A saved profile that later features (matching, tailoring) will read.

### 2.3 Resume upload and parsing (Available)

**Purpose:** Turn a PDF or DOCX resume into structured data without retyping it.

**How it works:**
1. The student uploads a PDF or DOCX of at most 5 MB. The file type is checked by its content, not only its name.
2. Text is extracted with PyMuPDF (PDF, handles multiple columns) or python-docx (DOCX, including tables and headers). Scanned image-only files are rejected with a clear message.
3. Google Gemini structures the text into contact details, summary, skills, education, experience, projects, certifications and achievements. The prompt tells it to copy only what is written.
4. A deterministic grounding check removes any skill, project technology or contact detail that does not appear in the resume text. What was removed is listed as notes.
5. If Gemini is unavailable, a simpler heuristic parser extracts contact details and recognised skills, and the resume is marked "partial". The student can re-run extraction later.

**How to use:** On "Profile & Resumes", choose a file and upload. Open "Resume Parsing" to see what was extracted. Use "Re-run extraction" to try again. A student can keep up to 10 resumes and choose which one is active.

**Output:** Structured resume data, a status (complete or partial), and a list of notes from the grounding check.

### 2.4 Skill review: extracted, verified, rejected (Available)

**Purpose:** Make sure only skills the student really has are used for matching.

**How it works:** Skills found in a resume are stored as **extracted**. The student can mark each one **verified** (confirmed) or **rejected** (wrong). Skills the student adds by hand are verified immediately. Re-running extraction never overrides a verify or reject decision. Skill names are normalised through an alias catalogue, so "JS" and "Javascript" become JavaScript and "k8s" becomes Kubernetes. Matching is by exact canonical name, never by substring, so "Java" does not match "JavaScript".

**How to use:** On "Resume Parsing", use the Skills panel: tick to verify, cross to reject, or type a skill to add it.

**Output:** Three lists (verified, extracted, rejected). Only verified skills are used by later analysis.

### 2.5 Internship knowledge base (Available)

**Purpose:** A searchable collection of internship postings.

**How it works:** The base holds 20 sample postings from fictional companies, each labelled "Sample", plus any postings the student adds. Each posting has a title, company, location, work mode (remote, on-site, hybrid), stipend, duration, education and experience requirements, and required and preferred skills. Postings the student adds are visible only to that student. Each posting is split into text chunks, converted to a vector with a local embedding model, and stored in the database. A search is converted to a vector the same way and compared by cosine similarity, so searching "build a chatbot over documents" finds a Generative AI internship even if the words differ. Filters (work mode, location, skill, sample or mine) combine with the search.

**How to use:** Open "Internship Knowledge Base". Type what you are looking for and press Search. Untick "Smart (semantic) search" for a plain title or company search. Use the filters to narrow results. Choose "Show details" to read a posting.

**Output:** A ranked list of postings with a relevance score and the best matching passage.

### 2.6 Add an internship from a job description (Available)

**Purpose:** Let a student add a real posting they found elsewhere without typing every field.

**How it works:** The student pastes the posting text. Gemini proposes the fields and which skills are required or preferred. A grounding check removes any value that is not in the pasted text. The result is shown as an editable draft, and nothing is saved until the student reviews it and presses Save. If Gemini is unavailable, only recognised skills are filled in and the student completes the rest.

**How to use:** On the knowledge base page choose "Add from job description", paste the text, choose "Extract details", correct any field, click a skill to switch it between required and preferred, then "Save internship". A student can delete postings they added. Sample postings cannot be deleted.

**Output:** A saved, searchable internship visible only to its creator.

### 2.7 Product Assistant (Available)

**Purpose:** Answer questions about how the product works, using this document as the only source.

**How it works:** Each question goes through a fixed pipeline: load this session's previous messages, rewrite a follow-up such as "why did we use it?" into a standalone question using the conversation, search this document by meaning for the five most relevant sections, and then ask the AI to answer using only those sections. The answer lists the sections it used as citations. If nothing in the document is relevant enough, the assistant says the information is not in the product documentation instead of guessing. Every message is saved with the student's ID and the session ID, and history is always fetched using both, so one student never sees another student's chats and one session never leaks into another. Long conversations are summarised so that earlier context is not lost.

**How to use:** Open "Product Assistant", start a new chat, and ask a question. Sessions appear in a list on the left, and a student can switch between them or delete them. The thumbs-up and thumbs-down buttons on an answer record feedback.

**Output:** An answer with citations to document sections, stored in the chat history.

### 2.8 Job matching (Planned)

**Purpose:** Show how well the student fits each internship, and why.

**How it works:** A deterministic scoring function (not the AI) compares the student's verified skills with each internship's required and preferred skills and also considers eligibility such as education. The score comes with a factor-by-factor breakdown listing matched and missing skills. The AI only writes the explanation, and if it fails the score and table are still shown.

**How to use:** Not yet available. It will be opened from "Job Matching".

**Output:** A score, a breakdown and a short explanation per internship.

### 2.9 Skill gap analysis (Planned)

**Purpose:** Show which skills are missing for a target internship or role and in what order to learn them.

**How it works:** The gap is computed by comparing verified skills with the target's required and preferred skills, ranked by importance. The AI then suggests a learning plan. No made-up courses or links are produced.

**How to use:** Not yet available. It will be opened from "Skill Gap".

**Output:** A ranked list of missing skills and a learning plan.

### 2.10 Resume and cover-letter tailoring (Planned)

**Purpose:** Adapt the student's resume points and a cover letter to a specific posting.

**How it works:** The AI drafts text from the student's verified profile and the posting. A fact guard then checks that every employer, title, date and skill in the output exists in the student's real profile and flags anything that does not. The student approves before anything is saved.

**How to use:** Not yet available. It will be opened from "Resume & Cover Letter".

**Output:** A tailored draft and a list of the facts it used.

### 2.11 Interview preparation (Planned)

**Purpose:** Practise for interviews with questions based on the role and the student's resume.

**How it works:** The AI generates questions, then scores and gives feedback on the student's typed answers against a rubric. Sessions are saved.

**How to use:** Not yet available. It will be opened from "Interview Prep".

**Output:** Questions, a rubric score and feedback.

### 2.12 Application tracker (Planned)

**Purpose:** Track every application from saved to offer.

**How it works:** Each application has a status (saved, applied, online assessment, interview, offer, rejected, withdrawn), dates and notes, and every status change is logged.

**How to use:** Not yet available. It will be opened from "Applications".

**Output:** A board or list of applications with history.

### 2.13 Career Assistant (Planned)

**Purpose:** A chat assistant that helps with the student's own career using their profile and the other tools.

**How it works:** It will be a LangGraph agent that can call tools such as reading the profile, searching internships, scoring a match and listing applications. Actions that change data will require confirmation. It is separate from the Product Assistant: it does not read this document, and the Product Assistant cannot see profile data.

**How to use:** Not yet available. It will be opened from "Career Assistant".

**Output:** Answers and tool results in a chat.

## 3. How to Use

### 3.1 Getting started step by step

1. Open the app and choose "Create one" to register, then sign in.
2. Open "Profile & Resumes" and fill in your profile, then save.
3. Upload your resume (PDF or DOCX, up to 5 MB).
4. Open "Resume Parsing", read what was extracted, and check any notes.
5. In the Skills panel, verify the skills that are true, reject the wrong ones, and add any that are missing.
6. Open "Internship Knowledge Base" and search or filter for internships.
7. Optionally add a posting by pasting its job description, reviewing the draft, and saving.
8. Open "Product Assistant" any time to ask how something works.

### 3.2 Asking the Product Assistant

1. Open "Product Assistant" and choose "New chat".
2. Type a question, for example "How does resume parsing work?".
3. Read the answer and the cited sections beneath it.
4. Ask a follow-up such as "Why was that approach used?". The assistant uses the conversation to understand "that".
5. Start another chat for a different topic. Chats are kept separate.

### 3.3 Common questions

**Why was a skill I did not list removed?** The grounding check removes any skill that does not appear in your resume text, to avoid invented skills.

**Why does the product not count extracted skills?** Only skills you confirm are treated as yours, so matching and gap analysis are based on what you stand behind.

**Are the sample internships real?** No. They come from fictional companies and are labelled "Sample". There is nothing to apply to.

**Who can see the internships I add?** Only you.

**What happens if the AI service is down?** Resume parsing falls back to a basic parser, job-description extraction fills in recognised skills only, and the Product Assistant reports an error rather than guessing.

## 4. Architecture

### 4.1 Overview

The product is a single-page web app talking to a REST API, which talks to a PostgreSQL database and to the Gemini AI service. Everything runs on the student's own computer except the database (Supabase) and Gemini.

```
Browser (React + Vite, localhost:5173)
   |  JSON over HTTP, /api/* proxied
   v
FastAPI backend (localhost:8000)
   |-- routers: auth, profile, resumes, skills, internships, chat/product
   |-- services: parsing, skills, internships, assistants
   |-- app/llm/client.py  --------> Google Gemini (structured JSON + text)
   |-- app/rag/*  (local fastembed model: embeddings, chunker, retriever)
   v
Supabase PostgreSQL + pgvector (session pooler)
```

### 4.2 Backend layers

Routers handle HTTP and validation. Services hold the logic. All AI calls go through one adapter module, so the provider can be swapped in one place. The retrieval code (chunker, embeddings, retriever) is shared by the internship search and the Product Assistant, using different corpora (`internship` and `product`).

### 4.3 RAG pipeline

Indexing: load the text, split it into overlapping chunks of about 1,200 characters at paragraph boundaries, embed each chunk with the BAAI bge-small-en-v1.5 model (384 dimensions, runs locally), and store text and vector in the `rag_chunks` table with an HNSW cosine index.

Answering: embed the question, retrieve the closest chunks by cosine similarity (best chunk per document, top 5), build a prompt containing the system rules, the conversation summary, recent history, the retrieved sections and the question, call Gemini, and return the answer with citations.

### 4.4 Product Assistant workflow

The Product Assistant is a LangGraph graph with five steps in a line: load history, condense question, retrieve, generate, persist. Condense rewrites a follow-up into a standalone question using prior messages. If retrieval finds nothing above the relevance threshold, the generate step is skipped and a fixed "not in the product documentation" reply is returned. No database transaction is held open while the AI is called.

### 4.5 Data model

Main tables: `users` and `refresh_tokens` (accounts), `student_profiles`, `resumes` and `resume_extractions`, `skills` and `student_skills` (status extracted, verified or rejected), `internships` and `internship_skills` (importance required or preferred), `rag_documents` and `rag_chunks` (retrieval index with vectors), `chat_sessions` (user, assistant type, title, summary), `chat_messages` (session, user, role, content, citations) and `message_feedback` (rating per message). Every table has row-level security enabled so the database's public REST interface exposes nothing.

### 4.5.1 Isolation of chats

Every chat query filters by user ID, session ID and assistant type together. A session belonging to another user or to another assistant is reported as not found.

### 4.6 Security

Passwords are hashed with bcrypt. Tokens are signed JWTs. Uploaded files are validated by content and size. Error messages do not echo submitted values. Every user-owned query is filtered by the signed-in user's ID.

## 5. Tech Stack

### 5.1 Why each technology was chosen

| Technology | Role | Why it was chosen |
|---|---|---|
| React 18 and Vite 5 | Frontend | A widely used component model with fast development reloads; Vite proxies `/api` to the backend so there are no cross-origin problems. |
| FastAPI | Backend API | Automatic request validation and interactive API docs, with Python's strong AI and data libraries. |
| SQLAlchemy 2 and Alembic | Data access and migrations | Typed models and versioned, repeatable schema changes. |
| PostgreSQL on Supabase | Database | A real relational database with a free hosted tier, so nothing has to be installed locally. |
| pgvector | Vector database | Keeps vectors in the same database as everything else, giving one datastore, transactions and joins, instead of running a separate vector store. It satisfies the requirement for a vector database. |
| fastembed with BAAI/bge-small-en-v1.5 | Embeddings | Small (about 130 MB), fast, runs locally on CPU with no API cost or rate limits, and gives good English retrieval quality at 384 dimensions. |
| Google Gemini 2.5 Flash | Language model | Fast, inexpensive, supports JSON-schema output for reliable extraction, and has a free tier. All calls go through one adapter. |
| LangGraph | Assistant workflow | Makes the assistant pipeline an explicit graph of small steps that are easy to test and extend; the planned Career Assistant needs tool loops that LangGraph handles well. |
| PyMuPDF and python-docx | Resume text extraction | Reliable PDF text extraction (including multiple columns) and DOCX reading, with no external services. |
| bcrypt and PyJWT | Authentication | Standard, well-reviewed password hashing and signed tokens. |
| pytest | Testing | Fast API tests against an in-memory database, plus integration tests against the real database. |

### 5.2 Why not a separate vector database such as Chroma or FAISS

They would add a second store to run and keep in sync. pgvector gives the same cosine search inside the existing database and is allowed as an alternative by the project brief.

### 5.3 Known limitations

Search relevance scores are similarities between 0 and 1, not probabilities. The assistant answers only from this document, so it cannot answer questions about things the document does not cover. Planned features are not available yet. Scanned (image-only) resumes are not supported because there is no OCR.

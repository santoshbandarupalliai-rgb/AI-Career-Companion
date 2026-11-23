# AI Career Companion: Agile Plan, Backlog and Retrospective

Written retrospectively from the finished work. It documents how the work was organised, not a day-by-day log.

## 1. Timeline and version-control note

- Project work started on **9 October 2026** (planning, research and prototyping).
- Source control with git began on **23 November 2026**. The commit history therefore shows the consolidated, rebuilt codebase from that date. It does not show the earlier exploration.
- Phases 1-9 below are the build order used in git. Milestone target dates are the student's own and are filled in Section 3 only where they are actually known.

## 2. Product vision and Definition of Done

**Vision:** a career companion that helps a student turn a resume into verified skills, find fitting internships, tailor application documents without invented facts, practise interviews, and track applications.

**Definition of Done (applied to every phase):** the phase check passes, automated tests exist and pass, the feature was verified in the browser, and the work is committed. No phase is built on a broken one.

## 3. Milestones

| # | Milestone | Phases | Delivered | Target date |
|---|---|---|---|---|
| M1 | Resume parser and APIs | 1 Foundation and auth, 2 Profile, resume upload, Gemini parsing, skill review | Yes | (student to fill) |
| M2 | Internship matching, RAG and cover-letter agent | 3 Knowledge base and semantic search, 5 Matching and skill gap, 6 Tailoring with fact guard and interview prep | Yes | (student to fill) |
| M3 | Product chatbot and assistants | 4 Product Knowledge Document and Product Assistant, 7 Application tracker and Career Assistant | Yes | (student to fill) |
| M4 | Final project | 8 Hardening, dashboard, error states, log redaction; 9 Docs, diagrams, demo script | Yes (real-Gemini testing pass still pending) | (student to fill) |

## 4. Epics and user stories

Acceptance criteria are the behaviours covered by the automated tests.

**E1 Accounts and profile**
- As a student, I can register and sign in securely so my data is private. *AC: passwords hashed, JWT with refresh, every query filtered by user.*
- As a student, I can save my education and target role. *AC: profile persists and drives matching.*

**E2 Resume and skills**
- As a student, I can upload a resume and see its structured content. *AC: PDF/DOCX parsed by Gemini, heuristic fallback if the model fails.*
- As a student, I can verify or reject extracted skills. *AC: only verified skills are used for matching and gaps.*

**E3 Internship knowledge base**
- As a student, I can browse and semantically search internships. *AC: samples labelled "Sample" with fictional companies; pgvector search.*
- As a student, I can add a posting by pasting a job description. *AC: draft shown for review, visible only to me.*

**E4 Matching and skill gap**
- As a student, I can see why a posting scores as it does. *AC: deterministic, explainable breakdown; missing information is not guessed.*
- As a student, I can see which skills I lack for a role or posting. *AC: ranked gaps and an optional learning plan.*

**E5 Application documents and interview prep**
- As a student, I can generate a tailored resume and cover letter that contain only true facts. *AC: fact guard flags unsupported claims; I approve before saving; .docx export.*
- As a student, I can practise interview questions and get rubric feedback. *AC: score out of 10 from a fixed rubric.*

**E6 Application tracker**
- As a student, I can track applications, statuses, notes and deadlines. *AC: status history, filters, upcoming deadlines.*

**E7 Assistants**
- As a user, I can ask how the product works and get cited answers. *AC: Product Assistant answers only from the Product Knowledge Document.*
- As a student, I can ask about my own career data and approve any change. *AC: Career Assistant proposes writes; only a click executes them.*

**E8 Quality and delivery**
- As an operator, I get clear error states and safe logs. *AC: "Cannot reach the server" message, request ids, redacted logs.*
- As a reviewer, I can understand and demo the system. *AC: README, diagrams, demo script, exported documents.*

## 5. Backlog status

| Item | Status |
|---|---|
| E1-E8 stories above | Done |
| Real-Gemini testing pass for Phases 4-7 (quota was exhausted) | Open |
| UI visual polish | Open |
| Verify Mermaid diagrams render | Open |
| PDF export of tailored resume, CV templates, streaming answers | Descoped (blueprint cut line) |

## 6. Retrospective (real lessons)

**Went well**
- Phase-by-phase delivery with a strict Definition of Done kept each layer stable (213 automated tests).
- Keeping scoring deterministic and the LLM only for wording made results explainable.
- Separating extracted from verified skills and adding a fact guard prevented invented claims.

**Problems and fixes**
- Gemini free-tier quota ran out during verification: tests use fakes, and a real-model testing pass is planned.
- Unreliable DNS on the development network: cached resolver, connect timeout and pooled pre-ping.
- Slow Gemini calls with thinking enabled: disabled for structured output.

**Next**
- Run the real-Gemini pass and fix prompts, then UI polish, then publish the repository.

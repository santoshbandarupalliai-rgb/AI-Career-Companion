# AI Career Companion: Product Knowledge Document

This document describes the AI Career Companion product. It is the only source the Product Assistant uses to answer questions about the product. Each feature is marked **Available** (works today) or **Planned** (designed but not built yet).

## 1. Overview

### 1.1 What the product is

AI Career Companion is a web application that helps students find and apply for internships. A student builds a profile, uploads a resume, confirms the skills found in it, browses an internship knowledge base, gets explainable match scores and skill-gap analysis, tailored resumes and cover letters, interview practice, and (in later releases) an application tracker and a chat-based Career Assistant.

### 1.2 Who it is for

It is built for students and recent graduates looking for internships, especially those who want guidance that is based on their real profile rather than generic advice.

### 1.3 Guiding principles

- **Nothing is invented.** A new profile starts empty. The product never makes up qualifications, internships, skills or eligibility.
- **Extracted is not verified.** Skills read from a resume are "extracted" until the student confirms them. Only "verified" skills count in matching and skill-gap analysis.
- **AI output is checked.** After the AI reads a document, a deterministic check removes anything that does not actually appear in the source text.
- **Sample data is labelled.** Demo internships come from fictional companies and carry a "Sample" badge.
- **Two separate assistants.** The Product Assistant (answers questions about the product from this document) and the Career Assistant (helps with the student's own career using their profile and the other tools) are different features with different data access.

### 1.4 Current release

The current release includes: sign-up and sign-in, the student profile, resume upload and parsing, skill review, the internship knowledge base with semantic search, job matching, skill gap analysis, resume and cover-letter tailoring, interview preparation, the application tracker, the Career Assistant and the Product Assistant, plus a dashboard with your progress and a suggested next step. All nine modules are available.

### 1.5 How the product works, step by step

In short, the product turns a student's resume into verified skills and then uses those skills to find, prepare for and track internship applications. The process, from the student's point of view:

1. **Create an account, verify the email address and fill in the profile** (college, degree, branch, graduation year, CGPA, target role).
2. **Upload a resume** (PDF or DOCX). The product reads it and extracts the contact details, education, experience, projects and skills.
3. **Review and verify the skills.** Skills found in the resume are only suggestions until the student verifies them. Only verified skills are used from here on.
4. **Browse or search internships** in the internship knowledge base, or add a posting by pasting a job description.
5. **See how well each internship matches.** Job matching gives a 0-100 score with a breakdown, and skill gap analysis shows which skills to learn next.
6. **Generate application documents.** For a chosen internship the product drafts a tailored resume or a cover letter from the student's real resume. The student reviews, edits and saves it.
7. **Prepare for interviews.** The Interview Prep Agent uses the resume data to recommend suitable roles and internships and prepares the student for them (questions, answer guidance, roadmap, learning path, and Q&A on uploaded documents). The mock interview scores the student's answers and gives a diagnostic report.
8. **Track applications.** The application tracker records each application's status, deadlines and notes.
9. **Ask for help.** The Career Assistant helps with the student's own search using their data, and the Product Assistant explains how the product works. The dashboard shows progress and the next suggested step.

## 2. Features

### 2.0 All features at a glance (Available)

The product has fifteen features, all available in the current release: account and sign-in, the student profile, resume upload and parsing, skill review, the internship knowledge base, adding an internship from a job description, job matching, skill gap analysis, resume and cover-letter tailoring, interview preparation, the application tracker, the Career Assistant, the Product Assistant, the dashboard and privacy protection for sensitive data. What each one does:

- **Account and sign-in:** register and sign in securely; each student only sees their own data. A verification email confirms the email address.
- **Student profile:** academic details and target role, empty until the student fills them in.
- **Resume upload and parsing:** upload PDF or DOCX resumes (up to 5 MB each, up to 10 resumes, each with an optional name such as "Backend resume") and have them structured automatically.
- **Skill review:** confirm, reject or add skills; only verified skills count.
- **Internship knowledge base:** browse and filter internships and search them by meaning (semantic search).
- **Add an internship from a job description:** paste a posting and review the extracted details before saving.
- **Job matching:** an explainable 0-100 compatibility score for each internship.
- **Skill gap analysis:** the skills missing for a role or an internship, ranked, with an optional learning plan.
- **Resume and cover-letter tailoring:** a resume or cover letter written for one chosen internship from the student's real resume, checked for invented facts.
- **Interview preparation:** an Interview Prep Agent chat that uses your resume data to recommend roles and internships, generates technical and HR questions, answer guidance, roadmaps and learning paths, and answers questions about PDF/DOCX documents you upload; plus a scored mock interview with a diagnostic report.
- **Application tracker:** statuses, deadlines, notes and a history of changes for each application.
- **Career Assistant:** a chat assistant that uses the student's own profile, matches and applications, only changes data after the student confirms, and stays within the internship search.
- **Product Assistant:** a chat assistant that answers questions about the product from this document, remembers the conversation, cites its sources and stays within the product.
- **Dashboard:** profile completeness, resume status, skills, applications, upcoming deadlines and a suggested next step.
- **Privacy protection:** national ids, card and bank numbers are masked before text goes to an AI service, and contact details are masked in what the student types.

### 2.1 Account and sign-in (Available)

**Purpose:** Keep each student's data private to them.

**How it works:** A student registers with a name, email and a password of at least 8 characters containing a letter and a number. Passwords are stored only as bcrypt hashes. After sign-in the app receives a short-lived access token (30 minutes) and a refresh token (7 days). The app renews the access token automatically, and only a genuine "not authenticated" answer signs the user out, so a network hiccup does not log anyone out.

**Email verification:** After registering, the student receives an email with a verification link that works once and expires after 24 hours. Opening the link confirms the address. Until then a banner on every page offers "Resend email" (one new email per minute; the newest link replaces older ones). The server can be set to require a verified email before anything else can be used; by default unverified students can still use the product. If the server has no email settings, the link is written to the server log instead of being emailed.

**How to use:** Open the app, choose "Create one" on the sign-in page, fill in the form, then sign in. Open the link in the verification email to confirm your address.

**Output:** A signed-in session, a verified email address and access to the student's own data only.

### 2.2 Student profile (Available)

**Purpose:** Hold the student's academic and career details in one place.

**How it works:** The profile has fields such as college, degree, branch, CGPA, graduation year, target role, location, bio and links (LinkedIn, GitHub, portfolio). It starts empty and is filled in only by the student: nothing is copied into the profile from an uploaded resume. Values are validated, for example CGPA must be within a sensible range and links must be valid.

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

**How to use:** On "Profile & Resumes", choose a file and upload. Open "Resume Parsing" to see what was extracted. Use "Re-run extraction" to try again. A student can keep up to 10 resumes, give each a name (for example "Backend resume" or "Data resume") with "Rename", and choose which one is active. The active resume is the default for matching, tailoring and interview practice; "Resume & Cover Letter", "Interview Prep" and the application form also let the student pick a different resume. Email addresses and phone numbers in a resume are replaced by placeholders before the text is sent to the AI service, and the real values are put back afterwards.

**Output:** Structured resume data, a status (complete or partial), and a list of notes from the grounding check.

### 2.4 Skill review: extracted, verified, rejected (Available)

**Purpose:** Make sure only skills the student really has are used for matching.

**How it works:** Skills found in a resume are stored as **extracted**. The student can mark each one **verified** (confirmed) or **rejected** (wrong). Skills the student adds by hand are verified immediately. Re-running extraction never overrides a verify or reject decision. Skill names are normalised through an alias catalogue, so "JS" and "Javascript" become JavaScript and "k8s" becomes Kubernetes. Matching is by exact canonical name, never by substring, so "Java" does not match "JavaScript".

**How to use:** On "Resume Parsing", use the Skills panel: tick to verify, cross to reject, or type a skill to add it.

**Output:** Three lists (verified, extracted, rejected). Only verified skills are used by later analysis.

### 2.5 Internship knowledge base (Available)

**Purpose:** A searchable collection of internship postings.

**How it works:** The base holds 20 sample postings from fictional companies, each labelled "Sample", plus any postings the student adds. Each posting has a title, company, location, work mode (remote, on-site, hybrid), stipend, duration, education and experience requirements, and required and preferred skills. Postings the student adds are visible only to that student. Each posting is split into text chunks, converted to a vector with a local embedding model, and stored in the database. A search is converted to a vector the same way and compared by cosine similarity, so searching "build a chatbot over documents" finds a Generative AI internship even if the words differ. Filters (work mode, location, skill, sample or mine) combine with the search.

**How to use:** Open "Internship Knowledge Base". Type what you are looking for and press Search. Untick "Smart (semantic) search" for a plain title or company search. Use the filters to narrow results. Choose "Show details" to read a posting. Choose "Apply" to apply to it (see "Apply option (demo)" below).

**Apply option (demo):** Each posting has an "Apply" button for demonstration purposes. It opens a small form where the student picks the resume to apply with (the active resume by default) and may add a note, then "Submit application". This records the application as Applied in the tracker, with today as the applied date and a history entry saying it was a demo. **Nothing is sent to any company**, because the sample postings are fictional. If the posting was already tracked as Saved it is moved to Applied; if it is already Applied or further along, the product says so and changes nothing. The card then shows "Applied (demo)".

**Output:** A ranked list of postings with a relevance score and the best matching passage.

### 2.6 Add an internship from a job description (Available)

**Purpose:** Let a student add a real posting they found elsewhere without typing every field.

**How it works:** The student pastes the posting text. Gemini proposes the fields and which skills are required or preferred. A grounding check removes any value that is not in the pasted text. The result is shown as an editable draft, and nothing is saved until the student reviews it and presses Save. If Gemini is unavailable, only recognised skills are filled in and the student completes the rest.

**How to use:** On the knowledge base page choose "Add from job description", paste the text, choose "Extract details", correct any field, click a skill to switch it between required and preferred, then "Save internship". A student can delete postings they added. Sample postings cannot be deleted.

**Output:** A saved, searchable internship visible only to its creator.

### 2.7 Product Assistant (Available)

**Purpose:** Answer questions about how the product works, using this document as the only source.

**How it works:** Each question goes through a fixed pipeline: load this session's previous messages, rewrite a follow-up such as "why did we use it?" into a standalone question using the conversation, search this document by meaning for the five most relevant sections, and then ask the AI to answer using only those sections. The answer lists the sections it used as citations. If nothing in the document is relevant enough, the assistant says the information is not in the product documentation instead of guessing. Every message is saved with the student's ID and the session ID, and history is always fetched using both, so one student never sees another student's chats and one session never leaks into another. Long conversations are summarised so that earlier context is not lost.

**How to use:** Choose "Product Assistant" in the header, start a new chat, and ask a question. Sessions appear in a list on the left, and a student can switch between them or delete them. The thumbs-up and thumbs-down buttons on an answer record feedback.

**Output:** An answer with citations to document sections, stored in the chat history.

### 2.8 Job matching (Available)

**Purpose:** Show how well each internship fits the student, and exactly why.

**How it works:** The score from 0 to 100 is calculated by fixed rules, never by the AI, so the same profile always gives the same score. It combines five factors: required skills (50%), preferred skills (15%), overall relevance of the student's profile text to the posting (20%), education fit (10%) and experience fit (5%). Skill factors are the share of the posting's required or preferred skills that are in the student's verified skills. Relevance is the similarity between a short text built from the student's target role, degree, branch and verified skills and the posting's text. Education fit compares the posting's stated requirement with the degree and branch in the profile. Experience fit checks, only when the posting asks for hands-on work, whether the active resume lists any projects or experience. Only verified skills count. Skills found in the resume but not yet verified are not scored, but the page lists them as a hint to verify. If a posting or profile does not give enough information for a factor, that factor is marked not applicable and its weight is shared among the others, and the page says so. Until the student verifies at least one skill, every score is 0. Eligibility details that a posting states, such as graduation years or a minimum CGPA, are shown as met, not met or unknown, but they are not part of the score. An optional "Explain in words" button asks the AI to describe the result in plain language using only the calculated facts; if the AI is unavailable, the score and breakdown are still shown.

**How to use:** Verify your skills first on "Resume Parsing", then open "Job Matching". Postings are listed from best to worst. Choose "Why this score?" to see the factor table, the matched and missing skills and the eligibility checks.

**Output:** A ranked list of internships with a score, a factor-by-factor breakdown with points, matched and missing skills, eligibility checks, and an optional AI explanation.

### 2.9 Skill gap analysis (Available)

**Purpose:** Show which skills the student is missing for a target and in what order to learn them.

**How it works:** The student picks either one specific internship or a target role. For a role, the product compares against the five closest postings in the knowledge base. The gap is computed by comparing verified skills with the posting skills, without AI. Missing skills are split into critical gaps (required by a posting) and secondary gaps (only preferred), and ranked by how many of the considered postings ask for them. A coverage percentage shows how much of the target's skill demand the verified skills cover, with preferred-only skills counting half. A missing skill that appears in the resume but is not verified is flagged so the student can verify it. An optional "Create learning plan" button asks the AI for one step per missing skill, with why it matters, what to study and a small practice project. The plan contains no links or course names, steps for skills that were not in the gap are discarded, and if the AI is unavailable the gap is still shown.

**How to use:** Open "Skill Gap", choose "A target role" and type a role, or choose "A specific internship". You can also open it from the "See skill gap" link in a match breakdown.

**Output:** Acquired skills, critical gaps, secondary gaps, a coverage percentage, and an optional learning plan.

### 2.10 Resume and cover-letter tailoring (Available)

**Purpose:** Adapt the student's resume and write a cover letter for a specific internship without inventing anything.

**How it works:** The student picks an internship and asks for a tailored resume or a cover letter. The AI is given only the student's real material: the posting, the verified skills, and the entries on the active resume. For the resume, the AI refers to the student's real experience and project entries by number and only rewrites their bullet points and a short summary. Employers, job titles, dates and project names are never written by the AI; they are copied from the resume. The skills list may contain only verified skills. A deterministic fact guard then checks everything the AI wrote and marks anything it cannot match: a number or year that is not in the profile or resume, a skill that is not verified (or was rejected), a proper name that is not in the profile, resume or posting, and a bullet that shares too little wording with the resume entry it came from. Marked items appear as "Check" notes next to the exact bullet or sentence, and unverified skills are removed from the skills list automatically. The result is only a draft: nothing is saved until the student edits it and approves it. When the student saves, the checks run again on what they submitted, so edits are checked too, entry details are copied from the resume again, and if anything is still flagged the student must confirm that it is accurate. Saved documents can be downloaded as Word (.docx) files. A student needs verified skills or a parsed resume first; if the AI is unavailable, no draft is produced and nothing is made up.

**How to use:** Open "Resume & Cover Letter", choose an internship, and choose "Tailor my resume" or "Write a cover letter". Read the draft, fix or delete anything marked "Check", then choose "Approve and save". Download or delete saved documents from the list below.

**Output:** A draft with notes on anything unsupported, the list of facts it is based on, and, once approved, a saved document that can be downloaded as .docx.

### 2.11 Interview preparation (Available)

**Purpose:** Help the student find the roles that suit their resume and prepare for interviews, and let them practise with scored answers.

**How it works:** The page has two parts.

*Interview Prep Agent (chat).* An AI agent that uses the student's extracted resume data as context: education, experience, projects, certifications and skills (verified skills, and skills listed on the resume but not yet verified, kept apart), the profile the student entered, and the internship matches calculated by the matching engine. Contact details are never sent to it. The student can ask:
- **Role recommendation:** "Which role can I apply for?", "Which internship is suitable for my skills?", "What are my strongest technical skills?". The agent explains each suggestion with evidence from the resume and recommends only internships from the knowledge base, with their real scores.
- **Interview preparation:** role-specific, technical and HR questions, guidance on how to answer them (for example the STAR method), topics to prepare, a week-by-week preparation roadmap and a learning path.
- **Document Q&A:** the student can upload up to 3 PDF or DOCX files (5 MB each) to a chat. The text is extracted, split into chunks and indexed with embeddings like the product knowledge base. Questions about the document are answered only from the most relevant excerpts, which are shown as sources, and the agent can generate practice questions with answers from the document. Documents belong to their chat and are deleted with it.
The agent remembers the conversation, so follow-ups such as "Give me HR questions for it" work. It stays within its area: unrelated questions get a fixed reply saying what it can help with, and attempts to change its instructions are refused. If the AI service fails, nothing is stored.

*Mock interview.* The student chooses a role or an internship (and a resume if they keep several) and a number of questions (5, 8 or 10). The AI writes the questions from the role, the posting, the verified skills and the real projects and experience on the resume, in four categories: technical, behavioral, situational and "about your resume". The session works like an interview chat: one question at a time, the student answers, and the interviewer replies with a score out of 10 from a fixed rubric (relevance and accuracy 0 to 4, structure and clarity 0 to 3, depth and examples 0 to 3), strengths, improvements and an outline of a strong answer. Questions can be skipped. An answer that only tries to instruct the evaluator is not sent to the AI and scores zero. A diagnostic report shows the overall level (Strong, Developing or Needs practice), the average per type of question, the strongest and weakest type, and the recurring strengths and improvements; it is calculated from the saved scores without AI. Scores are AI feedback, not an official grade.

**How to use:** Open "Interview Prep". On the "Prep Agent" tab choose a suggestion or type a question; choose "Upload PDF/DOCX" to add a document to the chat and then ask about it. On the "Mock interview" tab choose a role or an internship and "Start mock interview", answer each question with "Send answer" (or "Skip question"), and choose "Show diagnostic report".

**Output:** Saved chats with role recommendations, interview questions, roadmaps and document answers with sources; saved mock interviews with scores, feedback and a diagnostic report.

### 2.12 Application tracker (Available)

**Purpose:** Track every application from saved to offer, with a history of every status change.

**How it works:** Each application has a status (saved, applied, online assessment, interview, offer, rejected, withdrawn), an applied date, an optional deadline, the resume used and notes. An application can be linked to a posting from the internship knowledge base, in which case its company and role are copied from the posting and cannot be edited, or it can be an external application where the student types the company and role. A posting can be tracked only once. Every status change is recorded with the time, the old and new status and an optional note. Moving past "saved" sets the applied date to today if it was empty; the student can correct it. Any status can be changed to any other, so mistakes can be fixed, and the history keeps every step. Deadlines show how many days are left and are highlighted when three days or fewer remain.

**How to use:** On "Internship Knowledge Base", choose "Track" on a posting to add it as Saved, or "Apply" to record it as Applied (a demo: nothing is sent to the company). Or open "Applications" and choose "Add application" for an external posting. Change the status with the drop-down on each application; open "Details" to add a note for the next change, set dates, the resume used and notes, see the history, or remove the application. Use the status buttons at the top to filter. The Career Assistant can also propose adding or updating applications.

**Output:** A list of applications with counts per status and a full status history for each.

### 2.13 Career Assistant (Available)

**Purpose:** A chat assistant that helps with the student's own career: finding and comparing internships, explaining fit and skill gaps, preparing for interviews, and keeping the tracker up to date.

**How it works:** It is a LangGraph agent. For each message it decides, one step at a time, whether to call a tool or to answer, with at most four tool calls per message. Its tools are: read the profile and verified skills, search internships, rank the best matches, score one match in detail, analyse the skill gap for an internship or role, create interview practice questions (saved on the Interview Prep page), list applications, and propose a tracker change. The tools use the same rules as the rest of the product, so scores and gaps are identical to the Job Matching and Skill Gap pages, and only verified skills count. Every fact in an answer must come from a tool result; if a tool finds nothing, the assistant says so. The AI never sees database IDs: items it has seen get short codes that the server checks, so it cannot act on an item it was not shown. The assistant never changes data on its own. Adding an internship to the tracker or changing an application's status appears as a proposal under the answer with "Confirm" and "Cancel" buttons; nothing changes until the student confirms, and each proposal can be used once. Chats are saved per student with titles, memory of earlier messages (older messages are summarised), and 👍/👎 feedback. Each answer lists the tools it used. It is separate from the Product Assistant: it does not read this document, and the Product Assistant cannot see profile data.

**How to use:** Choose the green "Career Assistant" button at the bottom right of any page, then "New chat" or an example such as "Find internships that fit me and add the top one to my tracker", and read the answer. If it proposes a change, check it and choose "Confirm" or "Cancel". Expand "Used N tools" to see what it looked up. For questions about how the app works, use the Product Assistant.

**Output:** Answers grounded in the student's own data, tool traces, and confirmable tracker changes.

### 2.14 Dashboard (Available)

**Purpose:** Show the student where they stand and what to do next.

**How it works:** The dashboard reads the student's own data and shows four status cards: how many of six key profile fields are filled (college, degree, branch, graduation year, CGPA, target role), whether a resume is active, how many skills are verified and how many are waiting for review, and how many applications are tracked in each status. It lists up to five upcoming deadlines for applications that are still open. A "Next step" box suggests one action, the first one that is not yet done: upload a resume, review or add skills, complete the profile, view matches, follow up on a deadline, or practise interviews. The dashboard only reads data; it uses no AI and changes nothing. Only verified skills count towards matching, so the skills card makes that visible. The module list below the cards works as navigation.

**How to use:** Open "Dashboard" after signing in. Choose a card to go to the matching page, or choose the button in the "Next step" box.

**Output:** A status overview, upcoming deadlines and a suggested next step.

### 2.15 Privacy protection (Available)

**Purpose:** Keep sensitive personal data away from external AI services.

**How it works:** Before any text is sent to an AI service, the product masks sensitive identifiers: Aadhaar-style 12-digit ids, PAN numbers, card numbers (checked with the Luhn test), bank account numbers written next to a label, IFSC codes, passport numbers, US social security numbers and dates of birth written next to a label. They are replaced by markers such as [REDACTED_PAN]. For resumes, the email address and phone number are replaced by placeholders while the AI reads the resume, and the real values are restored in the result, so the contact fields still work. Contact details that a student types into a chat message or an interview answer are masked before they reach the AI. The messages as the student typed them are still shown in the student's own chat history. Masking is based on patterns, so it is a safety net and not a guarantee. It can be switched off with a server setting.

**How to use:** Nothing to do. Avoid typing sensitive numbers into chats.

**Output:** AI prompts that do not contain the masked identifiers.

## 3. How to Use

### 3.1 Getting started step by step

1. Open the app and choose "Create one" to register, then sign in. Open the link in the verification email to confirm your address.
2. Open "Profile & Resumes" and fill in your profile, then save.
3. Upload your resume (PDF or DOCX, up to 5 MB).
4. Open "Resume Parsing", read what was extracted, and check any notes.
5. In the Skills panel, verify the skills that are true, reject the wrong ones, and add any that are missing.
6. Open "Internship Knowledge Base" and search or filter for internships.
7. Optionally add a posting by pasting its job description, reviewing the draft, and saving.
8. Open "Job Matching" to see how well each internship fits you and why.
9. Open "Skill Gap" to see which skills to learn next for a role or an internship.
10. Open "Resume & Cover Letter" to tailor a resume or write a cover letter for an internship, review it, and save it.
11. Open "Interview Prep": ask the Prep Agent which roles suit you and how to prepare (you can also upload notes as PDF/DOCX and ask about them), then take a mock interview and open the diagnostic report.
12. Use "Track" on internships you are interested in, and keep their status up to date on "Applications".
13. Use the floating "Career Assistant" button (bottom right) to ask for help with your own search, for example which internships fit you and what to learn next.
14. Choose "Product Assistant" in the header any time to ask how something works.
15. Return to the "Dashboard" whenever you want to see your progress, upcoming deadlines and the suggested next step.

### 3.2 Asking the Product Assistant

1. Choose "Product Assistant" in the header and then "New chat".
2. Type a question, for example "How does resume parsing work?".
3. Read the answer and the cited sections beneath it.
4. Ask a follow-up such as "Why was that approach used?". The assistant uses the conversation to understand "that".
5. Start another chat for a different topic. Chats are kept separate.

### 3.3 Common questions

**Why was a skill I did not list removed?** The grounding check removes any skill that does not appear in your resume text, to avoid invented skills.

**Why does the product not count extracted skills?** Only skills you confirm are treated as yours, so matching and gap analysis are based on what you stand behind.

**Why is every match score 0?** Scores are only calculated once you have at least one verified skill. Verify your skills on the Resume Parsing page.

**Why did a skill from my resume not raise my score?** Only verified skills count. Unverified resume skills are listed as a hint on the match page.

**Can the AI add skills or experience I do not have to my resume?** No. Employers, titles and dates are copied from your resume, the skills list only contains verified skills, and anything the AI writes that cannot be matched to your profile or resume is flagged for you to fix before you can save.

**Are the sample internships real?** No. They come from fictional companies and are labelled "Sample". There is nothing to apply to.

**Who can see the internships I add?** Only you.

**Can the Career Assistant change my applications by itself?** No. It can only propose a change. Nothing is added or updated until you choose "Confirm" under its answer.

**What is the difference between the Career Assistant and the Product Assistant?** The Career Assistant works with your own profile, matches and applications. The Product Assistant answers questions about how the app works, only from this document, and cannot see your data.

**Why will the assistants not answer a general question?** Each assistant has one area. The Career Assistant only helps with your internship search, skills, applications and interview practice. The Product Assistant only answers questions about how this product works, from this document. Anything else gets a short reply saying what they can help with. They also refuse requests to ignore their rules or reveal their instructions.

**Is my personal data sent to the AI service?** Resume and chat text is sent to the AI service to generate answers. National id numbers, card and bank numbers, dates of birth and similar identifiers are masked first. Email addresses and phone numbers in a resume are replaced by placeholders, and contact details you type into a chat or an interview answer are masked. Masking is pattern based, so avoid typing sensitive numbers into the chat.

**Why do I see a banner asking me to verify my email?** Your email address has not been confirmed yet. Open the link in the verification email, or choose "Resend email" in the banner.

**Does my resume fill in my profile?** No. The profile is entered by you only. The resume is used for skills (which you verify) and as context for tailoring and interview preparation.

**What can the Interview Prep Agent do?** It recommends roles and internships that suit your resume, names your strongest skills, writes technical and HR questions with answer guidance, makes a preparation roadmap and learning path, and answers questions about PDF or DOCX files you upload to the chat.

**Can I keep more than one resume?** Yes, up to 10. Give each a name, choose which one is active, and pick a different one when you tailor a document or practise for an interview.

**What happens if the AI service is down?** If a second AI provider (Groq) is configured, the request is retried there automatically. If every provider fails, resume parsing falls back to a basic parser, job-description extraction fills in recognised skills only, and the Product Assistant and Career Assistant report an error rather than guessing; nothing is saved from a failed answer.

## 4. Architecture

### 4.1 Overview

The product is a single-page web app talking to a REST API, which talks to a PostgreSQL database and to the Gemini AI service, with an optional Groq service used as a fallback. Everything runs on the student's own computer except the database (Supabase) and the AI services.

```
Browser (React + Vite, localhost:5173)
   |  JSON over HTTP, /api/* proxied
   v
FastAPI backend (localhost:8000)
   |-- routers: auth, profile, resumes, skills, internships, matching, skill-gap, tailoring, interview, applications, chat/product, chat/career
   |-- services: parsing, skills, internships, match engine (pure rules), assistants
   |-- app/llm/client.py  --------> Google Gemini (structured JSON + text), then Groq as fallback
   |-- app/rag/*  (local fastembed model: embeddings, chunker, retriever)
   v
Supabase PostgreSQL + pgvector (session pooler)
```

### 4.2 Backend layers

Routers handle HTTP and validation. Services hold the logic. The match and skill-gap calculations are pure functions with no database or AI access, which makes them deterministic and easy to test; the AI is used only for the optional explanation and learning plan. All AI calls go through one adapter module, so the provider can be swapped in one place. The adapter tries the providers in a configured order (Gemini first, then Groq if a Groq key is set) and moves to the next one when a provider is rate-limited, unavailable or returns an answer in the wrong format. The retrieval code (chunker, embeddings, retriever) is shared by the internship search and the Product Assistant, using different corpora (`internship` and `product`).

### 4.3 RAG pipeline

Indexing: load the text, split it into overlapping chunks of about 1,200 characters at paragraph boundaries, embed each chunk with the BAAI bge-small-en-v1.5 model (384 dimensions, runs locally), and store text and vector in the `rag_chunks` table with an HNSW cosine index.

Answering: embed the question, retrieve the closest chunks by cosine similarity (best chunk per document, top 5), build a prompt containing the system rules, the conversation summary, recent history, the retrieved sections and the question, call Gemini, and return the answer with citations.

### 4.4 Product Assistant workflow

The Product Assistant is a LangGraph graph with five steps in a line: load history, condense question, retrieve, generate, persist. Condense rewrites a follow-up into a standalone question using prior messages. If retrieval finds nothing above the relevance threshold, the generate step is skipped and a fixed "not in the product documentation" reply is returned. No database transaction is held open while the AI is called.

### 4.4.1 Career Assistant workflow

The Career Assistant is a separate LangGraph graph: load context, then an agent step that either calls one tool or answers, looping through the tools step at most four times, then persist and summarise. Each agent step is one structured AI call. Tool errors are passed back to the AI as observations so it can recover or explain. Proposed tracker changes are stored on the answer as pending actions and are only carried out by a separate confirm request from the student.

### 4.5 Data model

Main tables: `users` and `refresh_tokens` (accounts), `student_profiles`, `resumes` and `resume_extractions`, `skills` and `student_skills` (status extracted, verified or rejected), `internships` and `internship_skills` (importance required or preferred), `rag_documents` and `rag_chunks` (retrieval index with vectors), `generated_documents` (approved resumes and cover letters, with the flags the student confirmed), `interview_sessions` and `interview_items` (questions, answers, scores, feedback), `applications` and `application_events` (tracked applications and their status history), `chat_sessions` (user, assistant type, title, summary), `chat_messages` (session, user, role, content, citations, tool steps and proposed actions) and `message_feedback` (rating per message). Every table has row-level security enabled so the database's public REST interface exposes nothing.

### 4.5.1 Isolation of chats

Every chat query filters by user ID, session ID and assistant type together. A session belonging to another user or to another assistant is reported as not found.

### 4.6 Security

AI-written resume and cover-letter text passes through a deterministic fact guard before the student can save it. Passwords are hashed with bcrypt. Tokens are signed JWTs. Uploaded files are validated by content and size. Error messages do not echo submitted values. Every user-owned query is filtered by the signed-in user's ID. The Career Assistant cannot write data: its proposals are executed only when the student confirms them, using parameters stored on the server. Email verification tokens are random, single-use, expire after 24 hours and are stored only as hashes. Sensitive identifiers are masked in every prompt sent to an AI service. Both assistants are limited to their own areas: a first check answers greetings and refuses attempts to change their rules without calling the AI, the Career Assistant must classify every message as in scope or out of scope, and the Product Assistant answers only from retrieved sections of this document. Refusals are fixed texts, not written by the AI.

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
| Groq (`openai/gpt-oss-120b`) | Fallback language model | Optional. Used only when Gemini is rate-limited or unavailable, so a free-tier limit does not stop the app. Its answers are checked against the same schemas. |
| LangGraph | Assistant workflow | Makes the assistant pipeline an explicit graph of small steps that are easy to test and extend; the Career Assistant uses a tool loop (agent step, tool, back to the agent) that LangGraph expresses directly. |
| PyMuPDF and python-docx | Resume text extraction | Reliable PDF text extraction (including multiple columns) and DOCX reading, with no external services. |
| bcrypt and PyJWT | Authentication | Standard, well-reviewed password hashing and signed tokens. |
| pytest | Testing | Fast API tests against an in-memory database, plus integration tests against the real database. |

### 5.2 Why not a separate vector database such as Chroma or FAISS

They would add a second store to run and keep in sync. pgvector gives the same cosine search inside the existing database and is allowed as an alternative by the project brief.

### 5.3 Known limitations

Search relevance scores are similarities between 0 and 1, not probabilities. A match score is a guide to fit, not a prediction of whether an employer will select the student. The assistant answers only from this document, so it cannot answer questions about things the document does not cover. Planned features are not available yet. Scanned (image-only) resumes are not supported because there is no OCR.

// Single source of truth for navigation. `phase` = build phase that delivers it.
export const MODULES = [
  { path: "/profile", label: "Profile & Resumes", num: 1, phase: 2, desc: "Your academic profile and resume versions." },
  { path: "/resume", label: "Resume Parsing", num: 2, phase: 2, desc: "Extracted skills, experience and projects, which you verify." },
  { path: "/internships", label: "Internship Knowledge Base", num: 3, phase: 3, desc: "Browse and semantically search internship postings." },
  { path: "/matching", label: "Job Matching", num: 4, phase: 5, desc: "Explainable compatibility scores against internships." },
  { path: "/skill-gap", label: "Skill Gap", num: 5, phase: 5, desc: "Missing skills ranked by importance, with a learning plan." },
  { path: "/customize", label: "Resume & Cover Letter", num: 6, phase: 6, desc: "Role-specific tailoring grounded in your real profile." },
  { path: "/interview", label: "Interview Prep", num: 7, phase: 6, desc: "Generated questions, practice answers and feedback." },
  { path: "/applications", label: "Applications", num: 8, phase: 7, desc: "Track every application from saved to offer." },
  { path: "/career-assistant", label: "Career Assistant", num: 9, phase: 7, desc: "A chat assistant that uses your profile and the tools above." },
  { path: "/product-assistant", label: "Product Assistant", num: null, phase: 4, desc: "Ask how Career Companion works, answered from its documentation." },
];

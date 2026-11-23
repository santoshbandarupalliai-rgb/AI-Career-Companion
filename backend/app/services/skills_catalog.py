"""Deterministic skill normalization.

Maps the many spellings of a skill ("JS", "Javascript", "javascript") to one
canonical key, so skills from resumes and internship postings can be compared
by exact match, never by substring (which would make "Java" match "JavaScript").
"""

import re

# canonical key -> (display name, category, aliases)
_CATALOG: dict[str, tuple[str, str, tuple[str, ...]]] = {
    # Languages
    "python": ("Python", "language", ("python3", "py")),
    "java": ("Java", "language", ("core java", "java se")),
    "javascript": ("JavaScript", "language", ("js", "java script", "ecmascript", "es6")),
    "typescript": ("TypeScript", "language", ("ts",)),
    "c": ("C", "language", ("c language", "c programming")),
    "c++": ("C++", "language", ("cpp", "c plus plus")),
    "c#": ("C#", "language", ("c sharp", "csharp")),
    "go": ("Go", "language", ("golang",)),
    "rust": ("Rust", "language", ()),
    "kotlin": ("Kotlin", "language", ()),
    "swift": ("Swift", "language", ()),
    "php": ("PHP", "language", ()),
    "ruby": ("Ruby", "language", ()),
    "r": ("R", "language", ("r programming", "r language")),
    "sql": ("SQL", "language", ("structured query language",)),
    "html": ("HTML", "language", ("html5",)),
    "css": ("CSS", "language", ("css3",)),
    "bash": ("Bash", "language", ("shell scripting", "shell", "bash scripting")),
    "matlab": ("MATLAB", "language", ()),
    "dart": ("Dart", "language", ()),
    # Frontend
    "react": ("React", "framework", ("react.js", "reactjs", "react js")),
    "next.js": ("Next.js", "framework", ("nextjs", "next js")),
    "angular": ("Angular", "framework", ("angularjs", "angular.js")),
    "vue.js": ("Vue.js", "framework", ("vue", "vuejs")),
    "redux": ("Redux", "framework", ()),
    "tailwind css": ("Tailwind CSS", "framework", ("tailwind", "tailwindcss")),
    "bootstrap": ("Bootstrap", "framework", ()),
    "flutter": ("Flutter", "framework", ()),
    "react native": ("React Native", "framework", ()),
    # Backend
    "node.js": ("Node.js", "framework", ("node", "nodejs", "node js")),
    "express.js": ("Express.js", "framework", ("express", "expressjs")),
    "fastapi": ("FastAPI", "framework", ("fast api",)),
    "django": ("Django", "framework", ()),
    "flask": ("Flask", "framework", ()),
    "spring boot": ("Spring Boot", "framework", ("springboot", "spring")),
    ".net": (".NET", "framework", ("dotnet", "asp.net", ".net core")),
    "rest api": ("REST APIs", "concept", ("rest", "restful", "rest apis", "restful apis", "restful api")),
    "graphql": ("GraphQL", "concept", ()),
    # Data / AI
    "machine learning": ("Machine Learning", "ai", ("ml",)),
    "deep learning": ("Deep Learning", "ai", ("dl",)),
    "natural language processing": ("NLP", "ai", ("nlp",)),
    "computer vision": ("Computer Vision", "ai", ("cv",)),
    "generative ai": ("Generative AI", "ai", ("genai", "gen ai")),
    "large language models": ("LLMs", "ai", ("llm", "llms")),
    "retrieval augmented generation": ("RAG", "ai", ("rag",)),
    "langchain": ("LangChain", "ai", ()),
    "langgraph": ("LangGraph", "ai", ()),
    "prompt engineering": ("Prompt Engineering", "ai", ()),
    "tensorflow": ("TensorFlow", "ai", ()),
    "pytorch": ("PyTorch", "ai", ("torch",)),
    "keras": ("Keras", "ai", ()),
    "scikit-learn": ("scikit-learn", "ai", ("sklearn", "scikit learn")),
    "hugging face": ("Hugging Face", "ai", ("huggingface", "hugging face transformers")),
    "pandas": ("Pandas", "data", ()),
    "numpy": ("NumPy", "data", ()),
    "matplotlib": ("Matplotlib", "data", ()),
    "data analysis": ("Data Analysis", "data", ("data analytics",)),
    "data visualization": ("Data Visualization", "data", ()),
    "power bi": ("Power BI", "data", ("powerbi",)),
    "tableau": ("Tableau", "data", ()),
    "excel": ("Excel", "data", ("ms excel", "microsoft excel", "advanced excel")),
    "statistics": ("Statistics", "data", ()),
    "apache spark": ("Apache Spark", "data", ("spark", "pyspark")),
    # Databases
    "postgresql": ("PostgreSQL", "database", ("postgres", "psql")),
    "mysql": ("MySQL", "database", ()),
    "mongodb": ("MongoDB", "database", ("mongo",)),
    "sqlite": ("SQLite", "database", ()),
    "redis": ("Redis", "database", ()),
    "firebase": ("Firebase", "database", ()),
    "vector databases": ("Vector Databases", "database", ("vector db", "vector database")),
    # Cloud / DevOps / tools
    "aws": ("AWS", "cloud", ("amazon web services",)),
    "microsoft azure": ("Azure", "cloud", ("azure",)),
    "google cloud": ("Google Cloud", "cloud", ("gcp", "google cloud platform")),
    "docker": ("Docker", "devops", ()),
    "kubernetes": ("Kubernetes", "devops", ("k8s",)),
    "ci/cd": ("CI/CD", "devops", ("cicd", "ci cd")),
    "github actions": ("GitHub Actions", "devops", ()),
    "jenkins": ("Jenkins", "devops", ()),
    "linux": ("Linux", "devops", ()),
    "git": ("Git", "tool", ()),
    "github": ("GitHub", "tool", ()),
    "postman": ("Postman", "tool", ()),
    "jira": ("Jira", "tool", ()),
    "figma": ("Figma", "tool", ()),
    "vs code": ("VS Code", "tool", ("vscode", "visual studio code")),
    # CS fundamentals
    "data structures and algorithms": ("Data Structures & Algorithms", "concept", ("dsa", "data structures", "algorithms", "data structures & algorithms")),
    "object-oriented programming": ("OOP", "concept", ("oop", "oops", "object oriented programming")),
    "dbms": ("DBMS", "concept", ("database management systems",)),
    "operating systems": ("Operating Systems", "concept", ("os",)),
    "computer networks": ("Computer Networks", "concept", ("cn", "networking")),
    "system design": ("System Design", "concept", ()),
    "unit testing": ("Unit Testing", "concept", ("testing",)),
    "pytest": ("pytest", "tool", ()),
    "agile": ("Agile", "concept", ("scrum", "agile methodology")),
    # Soft skills
    "communication": ("Communication", "soft", ("communication skills",)),
    "teamwork": ("Teamwork", "soft", ("team work", "collaboration", "team collaboration")),
    "leadership": ("Leadership", "soft", ()),
    "problem solving": ("Problem Solving", "soft", ("problem-solving",)),
    "time management": ("Time Management", "soft", ()),
}

# Short aliases are only trusted when the LLM/user gives them as a whole skill,
# never when scanning free text (e.g. "os", "cv", "r", "c" appear in ordinary words).
_AMBIGUOUS_FOR_SCAN = {"c", "r", "go", "os", "cv", "cn", "dl", "ml", "ts", "py", "js", "node", "spring",
                      "spark", "shell", "express", "rest", "testing", "networking", "mongo", "azure",
                      "collaboration", "swift", "ruby", "rust", "dart", "excel", "statistics", "torch"}

_ALIAS_TO_KEY: dict[str, str] = {}
for _key, (_name, _cat, _aliases) in _CATALOG.items():
    _ALIAS_TO_KEY[_key] = _key
    _ALIAS_TO_KEY[_name.lower()] = _key
    for _a in _aliases:
        _ALIAS_TO_KEY[_a] = _key


def _norm(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .,;:-–—()[]")


def canonicalize(raw: str) -> tuple[str, str, str | None] | None:
    """Return (canonical_key, display_name, category) for a skill string, or None if empty/junk."""
    n = _norm(raw)
    if not n or len(n) > 60:
        return None
    key = _ALIAS_TO_KEY.get(n)
    if key is None:
        # Try without a trailing version / ".js" variations, e.g. "python 3.11".
        stripped = re.sub(r"\s*v?\d+(\.\d+)*$", "", n)
        key = _ALIAS_TO_KEY.get(stripped)
    if key is not None:
        name, category, _ = _CATALOG[key]
        return key, name, category
    # Unknown skill: keep it, using its own normalized text as the key.
    display = re.sub(r"\s+", " ", raw.strip())[:100]
    return n, display, None


def find_known_skills(text: str) -> list[str]:
    """Scan free text for catalog skills (used by the no-LLM fallback). Returns canonical keys."""
    lowered = " " + re.sub(r"\s+", " ", text.lower()) + " "
    found: list[str] = []
    for alias, key in _ALIAS_TO_KEY.items():
        if alias in _AMBIGUOUS_FOR_SCAN or len(alias) < 3:
            continue
        pattern = r"(?<![a-z0-9+#.])" + re.escape(alias) + r"(?![a-z0-9+#])"
        if re.search(pattern, lowered) and key not in found:
            found.append(key)
    return found


def display_name(key: str) -> str:
    return _CATALOG[key][0] if key in _CATALOG else key


def category_of(key: str) -> str | None:
    return _CATALOG[key][1] if key in _CATALOG else None

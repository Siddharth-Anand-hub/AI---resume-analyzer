"""Resume analysis engine.

Two layers:
  1. A local, deterministic engine that actually reads the resume (sections,
     contact info, experience, impact, skills, wording) and scores it against
     the target role. Different resumes -> different scores and advice.
  2. An optional OpenAI layer that adds a written summary, tailored advice,
     roadmap and interview questions on top of the local facts.
     If there is no API key, or the call fails, the local result is returned.
"""
import json
import os
import re
from datetime import date

try:  # openai is optional; the local engine works without it
    from openai import OpenAI, OpenAIError
except Exception:  # pragma: no cover
    OpenAI = None

    class OpenAIError(Exception):
        pass

api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI() if (api_key and OpenAI) else None

# --------------------------------------------------------------------------
# Skill taxonomy: name -> (category, aliases)
# --------------------------------------------------------------------------
SKILLS = {
    # Languages
    "Python": ("Languages", ("python", "python3")),
    "Java": ("Languages", ("java",)),
    "JavaScript": ("Languages", ("javascript", "js", "es6", "ecmascript")),
    "TypeScript": ("Languages", ("typescript",)),
    "C++": ("Languages", ("c++",)),
    "C#": ("Languages", ("c#",)),
    "Go": ("Languages", ("golang", "go lang")),
    "Kotlin": ("Languages", ("kotlin",)),
    "Swift": ("Languages", ("swift", "swiftui")),
    "PHP": ("Languages", ("php", "laravel")),
    "R": ("Languages", ("r programming", "rstudio")),
    "Bash/Shell": ("Languages", ("bash", "shell scripting", "powershell", "scripting")),
    # Frontend
    "HTML": ("Frontend", ("html", "html5")),
    "CSS": ("Frontend", ("css", "css3", "sass", "scss")),
    "React": ("Frontend", ("react", "react.js", "reactjs", "redux")),
    "Angular": ("Frontend", ("angular", "angularjs")),
    "Vue": ("Frontend", ("vue", "vue.js", "vuejs")),
    "Tailwind CSS": ("Frontend", ("tailwind", "tailwindcss", "bootstrap")),
    "Next.js": ("Frontend", ("next.js", "nextjs")),
    "Accessibility": ("Frontend", ("accessibility", "wcag", "a11y")),
    "Responsive Design": ("Frontend", ("responsive design", "responsive", "mobile-first")),
    # Backend
    "Node.js": ("Backend", ("node.js", "nodejs", "express", "express.js")),
    "Flask": ("Backend", ("flask",)),
    "Django": ("Backend", ("django", "fastapi")),
    "Spring Boot": ("Backend", ("spring boot", "spring", "hibernate")),
    ".NET": ("Backend", (".net", "asp.net", "dotnet")),
    "REST APIs": ("Backend", ("rest api", "rest apis", "restful", "api development", "apis", "graphql")),
    "Microservices": ("Backend", ("microservices", "message queue", "kafka", "rabbitmq")),
    "Authentication": ("Backend", ("authentication", "oauth", "jwt", "authorization")),
    # Databases
    "SQL": ("Databases", ("sql", "mysql", "postgresql", "postgres", "sqlite", "oracle", "t-sql")),
    "MongoDB": ("Databases", ("mongodb", "nosql", "dynamodb", "cassandra")),
    "Redis": ("Databases", ("redis", "caching", "memcached")),
    "Database Design": ("Databases", ("database design", "data modeling", "data modelling", "schema design", "normalization")),
    # Cloud & DevOps
    "AWS": ("Cloud & DevOps", ("aws", "amazon web services", "ec2", "s3", "lambda")),
    "Azure": ("Cloud & DevOps", ("azure",)),
    "GCP": ("Cloud & DevOps", ("gcp", "google cloud")),
    "Docker": ("Cloud & DevOps", ("docker", "containers", "containerization")),
    "Kubernetes": ("Cloud & DevOps", ("kubernetes", "k8s", "helm")),
    "CI/CD": ("Cloud & DevOps", ("ci/cd", "jenkins", "github actions", "gitlab ci", "continuous integration")),
    "Terraform": ("Cloud & DevOps", ("terraform", "infrastructure as code", "ansible")),
    "Linux": ("Cloud & DevOps", ("linux", "unix", "ubuntu")),
    "Monitoring": ("Cloud & DevOps", ("monitoring", "prometheus", "grafana", "observability", "datadog")),
    # Data & ML
    "Pandas": ("Data & ML", ("pandas", "numpy")),
    "Statistics": ("Data & ML", ("statistics", "statistical analysis", "hypothesis testing", "a/b testing", "regression")),
    "Machine Learning": ("Data & ML", ("machine learning", "scikit-learn", "sklearn", "xgboost", "random forest")),
    "Deep Learning": ("Data & ML", ("deep learning", "pytorch", "tensorflow", "keras", "neural network", "neural networks", "cnn")),
    "NLP": ("Data & ML", ("nlp", "natural language processing", "transformers", "llm", "llms", "bert")),
    "Computer Vision": ("Data & ML", ("computer vision", "opencv", "image processing", "yolo")),
    "Model Evaluation": ("Data & ML", ("model evaluation", "cross-validation", "precision", "recall", "f1 score")),
    "MLOps": ("Data & ML", ("mlops", "model deployment", "mlflow", "model serving")),
    "Data Visualization": ("Data & ML", ("data visualization", "data visualisation", "tableau", "power bi", "powerbi", "matplotlib", "seaborn", "plotly", "looker")),
    "Data Cleaning": ("Data & ML", ("data cleaning", "data cleansing", "data wrangling", "etl", "data preprocessing")),
    "Excel": ("Data & ML", ("excel", "spreadsheets", "google sheets", "pivot tables", "vlookup")),
    "Big Data": ("Data & ML", ("spark", "pyspark", "hadoop", "airflow", "big data", "snowflake", "bigquery")),
    "Linear Algebra": ("Data & ML", ("linear algebra", "calculus", "probability")),
    # Mobile
    "Android": ("Mobile", ("android", "android studio", "jetpack compose")),
    "iOS": ("Mobile", ("ios", "xcode", "objective-c")),
    "Flutter": ("Mobile", ("flutter", "dart", "react native")),
    # Testing
    "Testing": ("Testing", ("testing", "unit tests", "unit testing", "pytest", "jest", "junit", "tdd", "integration testing")),
    "Test Automation": ("Testing", ("selenium", "cypress", "playwright", "test automation", "appium", "postman")),
    "QA Methodology": ("Testing", ("test cases", "test plans", "regression testing", "bug tracking", "qa", "quality assurance")),
    # Core CS / tools
    "Git": ("Tools", ("git", "github", "gitlab", "bitbucket", "version control")),
    "Data Structures": ("Core CS", ("data structures", "dsa")),
    "Algorithms": ("Core CS", ("algorithms", "leetcode", "competitive programming")),
    "System Design": ("Core CS", ("system design", "scalability", "distributed systems", "architecture")),
    "OOP": ("Core CS", ("oop", "object-oriented", "object oriented", "design patterns")),
    "Agile": ("Process", ("agile", "scrum", "kanban", "sprint")),
    "Jira": ("Tools", ("jira", "confluence", "trello", "asana")),
    # Design
    "Figma": ("Design", ("figma", "sketch", "adobe xd")),
    "User Research": ("Design", ("user research", "user interviews", "personas", "surveys")),
    "Wireframing": ("Design", ("wireframing", "wireframes", "information architecture")),
    "Prototyping": ("Design", ("prototyping", "prototypes", "interaction design")),
    "Usability Testing": ("Design", ("usability testing", "usability studies", "heuristic evaluation")),
    "Design Systems": ("Design", ("design system", "design systems", "ui kit", "visual design")),
    # Security
    "Networking": ("Security", ("networking", "tcp/ip", "dns", "firewall", "vpn")),
    "Security Fundamentals": ("Security", ("cybersecurity", "information security", "security fundamentals", "owasp", "penetration testing", "vulnerability")),
    "SIEM": ("Security", ("siem", "splunk", "elastic security", "qradar")),
    "Incident Response": ("Security", ("incident response", "incident handling", "threat hunting", "forensics")),
    "Cloud Security": ("Security", ("cloud security", "iam", "aws security", "azure security")),
    # Marketing
    "SEO": ("Marketing", ("seo", "search engine optimization", "keyword research")),
    "Content Marketing": ("Marketing", ("content marketing", "content strategy", "blogging")),
    "Marketing Analytics": ("Marketing", ("marketing analytics", "google analytics", "campaign analytics", "ga4")),
    "Paid Ads": ("Marketing", ("google ads", "facebook ads", "meta ads", "ppc", "sem", "paid media")),
    "Social Media": ("Marketing", ("social media", "instagram", "linkedin marketing")),
    "Email Marketing": ("Marketing", ("email marketing", "mailchimp", "hubspot", "crm")),
    "Copywriting": ("Marketing", ("copywriting", "copywriter", "content writing")),
    # Management
    "Project Planning": ("Management", ("project planning", "project management", "roadmap", "gantt", "pmp")),
    "Stakeholder Management": ("Management", ("stakeholder management", "stakeholders", "client management")),
    "Risk Management": ("Management", ("risk management", "risk assessment")),
    "Product Strategy": ("Management", ("product strategy", "product roadmap", "prd", "user stories", "go-to-market", "okrs", "kpis")),
    # Soft skills
    "Communication": ("Soft Skills", ("communication", "presentations", "technical writing", "public speaking")),
    "Leadership": ("Soft Skills", ("leadership", "led a team", "team lead", "managed a team", "mentored", "mentoring")),
    "Teamwork": ("Soft Skills", ("teamwork", "collaborated", "collaboration", "cross-functional")),
    "Problem Solving": ("Soft Skills", ("problem solving", "problem-solving", "troubleshooting", "debugging")),
}

# --------------------------------------------------------------------------
# Role profiles. skills: name -> weight (3 = critical, 2 = important, 1 = nice)
# --------------------------------------------------------------------------
ROLES = {
    "Frontend Developer": {
        "matches": ("frontend", "front end", "front-end", "web developer", "react developer", "ui developer", "web designer"),
        "skills": {"HTML": 3, "CSS": 3, "JavaScript": 3, "React": 3, "TypeScript": 2, "Responsive Design": 2,
                   "Git": 2, "Testing": 2, "REST APIs": 1, "Accessibility": 1, "Tailwind CSS": 1, "Next.js": 1},
        "questions": ("How would you make a complex web page fast on slow mobile connections?",
                      "How do you decide where state should live in a React/JavaScript application?",
                      "Walk me through how you would make a UI accessible to keyboard and screen-reader users."),
    },
    "Backend Developer": {
        "matches": ("backend", "back end", "back-end", "server side", "api developer", "python developer", "java developer", "node developer"),
        "skills": {"Python": 2, "Java": 2, "Node.js": 2, "REST APIs": 3, "SQL": 3, "Database Design": 2, "Authentication": 2,
                   "Git": 2, "Testing": 2, "Docker": 2, "System Design": 1, "Redis": 1, "Microservices": 1},
        "questions": ("How would you design a rate-limited, versioned REST API for this product?",
                      "How do you find and fix a slow database query in production?",
                      "How do you protect an API against common attacks like injection and broken auth?"),
    },
    "Full Stack Developer": {
        "matches": ("full stack", "full-stack", "fullstack", "mern", "mean stack"),
        "skills": {"HTML": 2, "CSS": 2, "JavaScript": 3, "React": 3, "Node.js": 2, "REST APIs": 3, "SQL": 3,
                   "Git": 2, "Authentication": 2, "Docker": 1, "Testing": 2, "TypeScript": 1, "MongoDB": 1},
        "questions": ("Describe how a request travels from the browser to your database and back.",
                      "How do you keep frontend and backend contracts in sync as a project grows?",
                      "How would you deploy and monitor a full-stack app with zero downtime?"),
    },
    "Data Analyst": {
        "matches": ("data analyst", "business analyst", "business intelligence", "bi analyst", "analytics", "reporting analyst"),
        "skills": {"SQL": 3, "Excel": 3, "Data Visualization": 3, "Statistics": 2, "Python": 2, "Data Cleaning": 2,
                   "Communication": 2, "Pandas": 1, "Marketing Analytics": 1},
        "questions": ("A key metric dropped 15% overnight. How do you investigate?",
                      "How do you explain a statistical finding to a non-technical stakeholder?",
                      "How would you validate that a dataset is clean enough to report on?"),
    },
    "Data Scientist": {
        "matches": ("data scientist", "data science"),
        "skills": {"Python": 3, "SQL": 2, "Statistics": 3, "Pandas": 3, "Machine Learning": 3, "Data Visualization": 2,
                   "Model Evaluation": 2, "Data Cleaning": 2, "Deep Learning": 1, "Big Data": 1},
        "questions": ("How would you choose and evaluate a model for an imbalanced dataset?",
                      "How do you detect data leakage in a modelling pipeline?",
                      "Explain bias vs. variance and how it changes your modelling choices."),
    },
    "Machine Learning Engineer": {
        "matches": ("machine learning", "ml engineer", "ai engineer", "artificial intelligence", "deep learning", "mlops"),
        "skills": {"Python": 3, "Machine Learning": 3, "Deep Learning": 3, "Model Evaluation": 2, "MLOps": 2, "Statistics": 2,
                   "Linear Algebra": 2, "Docker": 2, "Git": 1, "NLP": 1, "Computer Vision": 1, "Big Data": 1},
        "questions": ("How would you decide a model is ready for production?",
                      "What would you do if model accuracy dropped weeks after deployment?",
                      "How do you serve a large model with low latency and a controlled cost?"),
    },
    "DevOps / Cloud Engineer": {
        "matches": ("devops", "cloud engineer", "site reliability", "sre", "platform engineer", "infrastructure engineer"),
        "skills": {"Linux": 3, "Docker": 3, "Kubernetes": 2, "CI/CD": 3, "AWS": 3, "Terraform": 2, "Bash/Shell": 2,
                   "Monitoring": 2, "Git": 2, "Python": 1, "Networking": 1, "Azure": 1, "GCP": 1},
        "questions": ("Describe a CI/CD pipeline you would build for a microservice, end to end.",
                      "How do you debug a container that keeps restarting in production?",
                      "How would you design monitoring and alerting so that alerts are actionable?"),
    },
    "Mobile App Developer": {
        "matches": ("mobile", "android developer", "ios developer", "app developer", "flutter developer"),
        "skills": {"Kotlin": 2, "Java": 1, "Swift": 2, "Android": 2, "iOS": 2, "Flutter": 2, "REST APIs": 3, "Git": 2,
                   "Testing": 2, "Authentication": 1, "Data Structures": 1},
        "questions": ("How do you handle offline mode and sync conflicts in a mobile app?",
                      "How do you keep a mobile app smooth when loading large lists and images?",
                      "How would you structure a mobile codebase for testability?"),
    },
    "QA / Test Engineer": {
        "matches": ("qa", "quality assurance", "test engineer", "sdet", "tester", "automation tester"),
        "skills": {"QA Methodology": 3, "Test Automation": 3, "Testing": 3, "SQL": 2, "Git": 2, "Agile": 2, "Jira": 2,
                   "Python": 1, "Java": 1, "CI/CD": 1, "Communication": 1},
        "questions": ("How do you decide what to automate and what to keep manual?",
                      "A bug only appears in production. How do you reproduce and isolate it?",
                      "How do you design a regression suite that stays fast and reliable?"),
    },
    "UX / Product Designer": {
        "matches": ("ux", "ui designer", "product designer", "user experience", "user interface", "ui/ux", "graphic designer"),
        "skills": {"Figma": 3, "User Research": 3, "Wireframing": 3, "Prototyping": 3, "Usability Testing": 2,
                   "Design Systems": 2, "Accessibility": 2, "Communication": 2, "HTML": 1, "CSS": 1},
        "questions": ("Walk me through a design decision you changed because of user research.",
                      "How would you test whether a prototype actually solves the user's problem?",
                      "How do you handle disagreement with a stakeholder about a design direction?"),
    },
    "Cybersecurity Analyst": {
        "matches": ("cybersecurity", "cyber security", "security analyst", "information security", "soc analyst", "penetration", "ethical hacker"),
        "skills": {"Networking": 3, "Linux": 2, "Security Fundamentals": 3, "SIEM": 2, "Incident Response": 3,
                   "Bash/Shell": 2, "Python": 1, "Cloud Security": 2, "Authentication": 1},
        "questions": ("How would you triage and prioritise a flood of security alerts?",
                      "Walk me through containing a suspected compromised host.",
                      "How do you explain a security risk to leadership who must decide on budget?"),
    },
    "Digital Marketer": {
        "matches": ("marketing", "seo", "digital marketer", "content strategist", "growth", "social media manager"),
        "skills": {"SEO": 3, "Content Marketing": 2, "Marketing Analytics": 3, "Social Media": 2, "Email Marketing": 2,
                   "Paid Ads": 2, "Copywriting": 2, "Communication": 2, "Excel": 1},
        "questions": ("How would you measure the success of a campaign beyond clicks?",
                      "A campaign is under target halfway through. What do you change?",
                      "How do you decide how to split budget between channels?"),
    },
    "Project / Product Manager": {
        "matches": ("project manager", "project management", "scrum master", "product manager", "program manager", "product owner"),
        "skills": {"Agile": 3, "Project Planning": 3, "Stakeholder Management": 3, "Risk Management": 2, "Jira": 2,
                   "Communication": 3, "Leadership": 2, "Product Strategy": 2, "Excel": 1},
        "questions": ("A project is about to miss its deadline. What do you do in the first 48 hours?",
                      "How do you handle two stakeholders with conflicting priorities?",
                      "How do you decide what NOT to build?"),
    },
    "Software Engineer": {
        "matches": ("software engineer", "software developer", "programmer", "developer", "engineer", "sde", "swe"),
        "skills": {"Data Structures": 3, "Algorithms": 3, "OOP": 2, "Git": 3, "SQL": 2, "Testing": 2, "REST APIs": 2,
                   "Problem Solving": 2, "System Design": 1, "Docker": 1, "Python": 1, "Java": 1},
        "questions": ("How do you approach debugging an unfamiliar codebase?",
                      "How do you balance code quality with delivery deadlines?",
                      "Explain a trade-off you made between simplicity and performance."),
    },
}

# --------------------------------------------------------------------------
# Language resources
# --------------------------------------------------------------------------
STRONG_VERBS = {
    "built", "developed", "designed", "implemented", "created", "led", "launched", "optimized", "optimised",
    "reduced", "increased", "improved", "automated", "deployed", "architected", "delivered", "migrated",
    "analyzed", "analysed", "engineered", "established", "streamlined", "managed", "mentored", "integrated",
    "refactored", "scaled", "spearheaded", "generated", "boosted", "achieved", "trained", "resolved", "drove",
    "coordinated", "negotiated", "secured", "researched", "published", "won", "founded",
}
WEAK_PHRASES = (
    "responsible for", "worked on", "helped with", "helped to", "duties included", "assisted in", "assisted with",
    "involved in", "tasked with", "hard working", "hardworking", "team player", "good communication skills",
    "quick learner", "detail oriented", "detail-oriented", "references available",
)
SECTION_HEADINGS = {
    "summary": ("summary", "profile", "objective", "career objective", "professional summary", "about me", "about"),
    "experience": ("experience", "work experience", "professional experience", "employment", "work history", "internship", "internships"),
    "education": ("education", "academic", "qualification", "qualifications", "academics"),
    "skills": ("skills", "technical skills", "key skills", "core competencies", "technologies", "tech stack"),
    "projects": ("projects", "academic projects", "personal projects", "key projects"),
    "certifications": ("certifications", "certificates", "courses", "licenses", "training"),
    "achievements": ("achievements", "awards", "honors", "honours", "accomplishments", "publications", "extracurricular"),
}
SKILL_PROJECTS = {
    "Java": "build a REST service with Spring Boot, JPA and unit tests, and document it with OpenAPI",
    "Node.js": "build an Express API with validation, error handling and a database layer",
    "Python": "automate a real task end to end with a script plus tests, then package it as a small CLI",
    "JavaScript": "build a vanilla-JS app (no framework) with fetch, DOM updates and local state",
    "HTML": "hand-code a semantic, accessible multi-section page without a framework",
    "CSS": "recreate a real landing page using flexbox and grid only",
    "Responsive Design": "make one of your pages fully usable from 320px to 1440px wide",
    "Accessibility": "audit a page with Lighthouse and axe, then fix every critical issue",
    "Database Design": "design a normalised schema for a booking app and justify each index",
    "Microservices": "split a small monolith into two services that talk through a message queue",
    "Redis": "add Redis caching to a slow endpoint and measure the latency drop",
    "MongoDB": "model a content app in MongoDB and compare it with a relational design",
    "Flask": "ship a small Flask app with blueprints, auth and a deployed demo",
    "Django": "build a Django app with the admin, models and a REST API",
    "Next.js": "build a Next.js site with server-side rendering and an API route",
    "Tailwind CSS": "rebuild a dashboard layout using only Tailwind utility classes",
    "Android": "build and publish an Android app that uses a REST API and local storage",
    "iOS": "build an iOS app with SwiftUI that persists data locally",
    "Flutter": "build a cross-platform app with state management and an API call",
    "Kotlin": "rewrite a small Java/Android feature in Kotlin with coroutines",
    "Swift": "build a small SwiftUI app and write unit tests for its view model",
    "Test Automation": "automate the login and checkout flow of a demo site with Playwright or Selenium",
    "QA Methodology": "write a test plan and 30 test cases for a real app and log the bugs you find",
    "Prototyping": "build a clickable prototype and test it with 3 people",
    "Wireframing": "produce low-fidelity wireframes for a 4-screen flow and get written feedback",
    "Usability Testing": "run 5 moderated usability tests and report the top 3 findings",
    "Design Systems": "create a small design system with tokens, 10 components and usage notes",
    "Content Marketing": "plan and publish a 4-post content series, then report reach and engagement",
    "Email Marketing": "design a 3-email nurture sequence and measure open and click rates",
    "Paid Ads": "run a small paid campaign with a fixed budget and report CPA and ROAS",
    "Social Media": "grow a niche account with a 30-day posting plan and track the metrics",
    "Copywriting": "rewrite three landing pages and A/B test the headlines",
    "Stakeholder Management": "write a stakeholder map and a communication plan for a current project",
    "Risk Management": "build a risk register with probability, impact and mitigations for a project",
    "Project Planning": "plan a small project with milestones, dependencies and a Gantt chart",
    "Product Strategy": "write a one-page PRD with user stories and success metrics for a feature idea",
    "Communication": "present a technical topic to non-experts in 5 minutes and collect feedback",
    "Leadership": "lead a small project or study group and write down what you would change",
    "Jira": "run a small project on a Jira board with epics, sprints and a burndown report",
    "Bash/Shell": "write shell scripts that automate backups and log rotation",
    "Monitoring": "set up Prometheus and Grafana dashboards with two meaningful alerts",
    "Azure": "deploy a web app and database on Azure using the free tier",
    "GCP": "deploy a containerised service on Cloud Run with a managed database",
    "Incident Response": "run a tabletop exercise and write a post-incident report",
    "Security Fundamentals": "complete an OWASP Top 10 lab series and summarise each fix",
    "Cloud Security": "audit IAM roles in a sandbox cloud account and apply least privilege",
    "OOP": "refactor a script into classes using two design patterns, with tests",
    "Problem Solving": "solve 30 mixed-difficulty problems and write down your approach for each",
    "Linear Algebra": "implement linear regression and PCA from scratch with NumPy",
    "Model Evaluation": "compare models with cross-validation and report precision, recall and F1",
    "Computer Vision": "train an image classifier and explain where it fails",
    "NLP": "build a text classifier or a retrieval-based Q&A demo over your own documents",
    "Big Data": "process a multi-GB dataset with PySpark and schedule it in Airflow",
    "Data Cleaning": "clean a messy public dataset and document every decision you made",
    "Docker": "containerise a small web app and its database with docker-compose",
    "Kubernetes": "deploy a 2-service app to a local kind/minikube cluster with a Helm chart",
    "AWS": "host a static site + API on S3, Lambda and API Gateway using the free tier",
    "CI/CD": "add a GitHub Actions pipeline that tests, builds and deploys one of your repos",
    "Terraform": "provision a VPC and a small server entirely with Terraform",
    "SQL": "model a 5-table database and answer 15 business questions with joins and window functions",
    "React": "build a small dashboard with routing, forms and API calls",
    "TypeScript": "convert one of your JavaScript projects to TypeScript with strict mode",
    "Testing": "reach 80% test coverage on one existing project and add tests to CI",
    "Git": "contribute a pull request to an open-source repo and use feature branches on your own repos",
    "REST APIs": "design and document a CRUD API with authentication and pagination",
    "Authentication": "add JWT or OAuth login, with roles, to a project",
    "Machine Learning": "train, tune and compare three models on a public Kaggle dataset",
    "Deep Learning": "fine-tune a small neural network on an image or text dataset",
    "Statistics": "run an A/B test analysis, with confidence intervals, on a public dataset",
    "Data Visualization": "publish a Tableau / Power BI dashboard answering a clear business question",
    "Pandas": "clean and analyse a messy real-world CSV and publish the notebook",
    "Excel": "build a pivot-table and lookup-based report from a raw sales export",
    "MLOps": "serve a model behind an API with MLflow tracking and a Docker image",
    "Figma": "redesign one screen of a real app and build a clickable prototype",
    "User Research": "run 5 user interviews and write up the insights and next steps",
    "SEO": "audit a small website and improve its rankings for 5 target keywords",
    "Marketing Analytics": "set up GA4 for a demo site and build a conversion funnel report",
    "Agile": "run a 2-week sprint on a side project with a board, planning and retro",
    "System Design": "write a design doc for a URL shortener covering scale, caching and failure modes",
    "Data Structures": "solve 40 curated problems on arrays, trees and graphs and write up the patterns",
    "Algorithms": "solve 40 curated problems on sorting, DP and graphs and write up the patterns",
    "Linux": "set up and harden a small VPS, using only the command line",
    "Networking": "capture and explain DNS, TCP and HTTP traffic with Wireshark",
    "SIEM": "ingest sample logs into Splunk/Elastic and build 3 detection rules",
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _has_term(text_lower, term):
    pattern = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
    return re.search(pattern, text_lower) is not None


def _skill_hits(text_lower):
    """Return {skill: number of mentions} for skills found in the resume."""
    found = {}
    for skill, (_, aliases) in SKILLS.items():
        count = 0
        for alias in aliases:
            pattern = r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])"
            count += len(re.findall(pattern, text_lower))
        if count:
            found[skill] = count
    return found


def _find_sections(text):
    found = {}
    for raw in text.splitlines():
        line = raw.strip().strip(":-–|#* ").lower()
        if not line or len(line) > 40:
            continue
        for key, names in SECTION_HEADINGS.items():
            if line in names and key not in found:
                found[key] = True
    return found


def _section_body(text, key):
    """Return the lines under the heading for `key` (until the next heading)."""
    all_names = {n for names in SECTION_HEADINGS.values() for n in names}
    lines = text.splitlines()
    body, active = [], False
    for raw in lines:
        clean = raw.strip().strip(":-–|#* ").lower()
        if clean and len(clean) <= 40 and clean in all_names:
            active = clean in SECTION_HEADINGS[key]
            continue
        if active and raw.strip():
            body.append(raw.strip())
    return body


def _contact_info(text):
    return {
        "email": bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)),
        "phone": bool(re.search(r"(\+?\d[\d\s().-]{8,}\d)", text)),
        "linkedin": "linkedin.com" in text.lower(),
        "github": "github.com" in text.lower(),
        "portfolio": bool(re.search(r"(portfolio|behance|dribbble|medium\.com|kaggle\.com)", text.lower())),
    }


_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"


def _experience_years(text):
    """Estimate years of experience from date ranges, falling back to 'X years'."""
    this_year = date.today().year
    spans = []
    pattern = re.compile(
        rf"((?:{_MONTHS})[a-z]*\.?\s+)?((?:19|20)\d{{2}})\s*(?:-|–|—|to)\s*"
        rf"(?:((?:{_MONTHS})[a-z]*\.?\s+)?((?:19|20)\d{{2}})|(present|current|now|ongoing))",
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        start = int(m.group(2))
        end = this_year if m.group(5) else int(m.group(4))
        if 1990 <= start <= end <= this_year + 1:
            spans.append((start, end))
    spans.sort()
    merged = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    from_dates = sum(e - s for s, e in merged)
    stated = [int(x) for x in re.findall(r"(\d{1,2})\+?\s*(?:years|yrs)", text.lower()) if int(x) < 40]
    years = max([from_dates] + stated) if (from_dates or stated) else 0
    return years


def _education(text_lower):
    levels = (
        ("PhD", ("phd", "ph.d", "doctorate")),
        ("Master's", ("master", "m.tech", "mtech", "m.sc", "msc", "mba", "m.e.", "mca", "m.s.")),
        ("Bachelor's", ("bachelor", "b.tech", "btech", "b.e.", "b.sc", "bsc", "bca", "b.com", "bba", "b.a.", "b.s.")),
        ("Diploma", ("diploma",)),
    )
    for label, keys in levels:
        if any(_has_term(text_lower, k) for k in keys):
            return label
    return None


def _lines(text):
    return [l.strip() for l in text.splitlines() if l.strip()]


_BULLET = re.compile(r"^[\-•*▪●–·►➢✓]\s*")
_QUANT = re.compile(r"(\d+\s?%|\$\s?\d|₹\s?\d|\d+\s?[kKmMxX]\b|\b\d{2,}\+?\s+(?:users|customers|clients|requests|records|students|projects|members|engineers|downloads|sales|leads)|\b\d+(?:\.\d+)?\s?(?:x|times)\b)")


def _impact_metrics(text):
    lines = _lines(text)
    bullets = [_BULLET.sub("", l) for l in lines if _BULLET.match(l)]
    statements = bullets or [l for l in lines if len(l) > 45]
    quantified = [s for s in statements if _QUANT.search(s)]
    strong, weak_found = 0, []
    for s in statements:
        words = s.lower().split()
        if words and words[0].strip(",.") in STRONG_VERBS:
            strong += 1
    low = text.lower()
    for phrase in WEAK_PHRASES:
        if phrase in low:
            weak_found.append(phrase)
    return {
        "bullets": len(bullets),
        "statements": len(statements),
        "quantified": len(quantified),
        "quantified_examples": [s[:110] for s in quantified[:2]],
        "strong_verbs": strong,
        "weak_phrases": weak_found,
        "weak_examples": [s[:110] for s in statements if any(p in s.lower() for p in WEAK_PHRASES)][:2],
    }


def _project_names(text):
    names = []
    for line in _section_body(text, "projects"):
        if _BULLET.match(line):
            continue
        head = re.split(r"\s[-–—|:]\s|:\s", line)[0].strip()
        if 3 <= len(head) <= 60:
            names.append(head)
    return names[:3]


def _select_role(goal):
    g = f" {goal.lower()} "
    for generic_pass in (False, True):
        best_name, best_len = None, 0
        for name, role in ROLES.items():
            if (name == "Software Engineer") != generic_pass:
                continue
            for m in role["matches"]:
                if _has_term(g, m) and len(m) > best_len:
                    best_name, best_len = name, len(m)
        if best_name:
            return best_name
    return None


def _closest_role_by_resume(found_skills):
    best, best_score = "Software Engineer", -1
    for name, role in ROLES.items():
        total = sum(role["skills"].values())
        got = sum(w for s, w in role["skills"].items() if s in found_skills)
        score = got / total if total else 0
        if score > best_score:
            best, best_score = name, score
    return best


def _level(years):
    if years < 1:
        return "Entry level / fresher"
    if years < 3:
        return "Junior"
    if years < 6:
        return "Mid level"
    return "Senior"


def _verdict(score):
    if score >= 80:
        return "Strong match"
    if score >= 65:
        return "Good match"
    if score >= 50:
        return "Moderate match"
    if score >= 35:
        return "Needs work"
    return "Weak match"


# --------------------------------------------------------------------------
# Local analysis
# --------------------------------------------------------------------------
def _build_local_analysis(resume_text, user_goal):
    text = resume_text or ""
    low = text.lower()
    hits = _skill_hits(low)
    role_name = _select_role(user_goal)
    role_matched = role_name is not None
    if not role_name:
        role_name = _closest_role_by_resume(hits)
    role = ROLES[role_name]
    weights = role["skills"]

    # --- skills vs role ---------------------------------------------------
    total_w = sum(weights.values())
    got_w = sum(w for s, w in weights.items() if s in hits)
    skill_ratio = got_w / total_w if total_w else 0
    matched = sorted([s for s in weights if s in hits], key=lambda s: (-weights[s], s))
    missing = sorted([s for s in weights if s not in hits], key=lambda s: (-weights[s], s))
    other_skills = sorted([s for s in hits if s not in weights], key=lambda s: -hits[s])
    all_skills = matched + other_skills

    # --- structure --------------------------------------------------------
    sections = _find_sections(text)
    contact = _contact_info(text)
    words = len(re.findall(r"\w+", text))
    years = _experience_years(text)
    edu = _education(low)
    impact = _impact_metrics(text)
    projects = _project_names(text)

    # --- scores -----------------------------------------------------------
    skill_score = round(skill_ratio * 40)

    exp_part = min(1.0, years / 3) * 0.6
    exp_part += 0.2 if sections.get("experience") or years else 0
    exp_part += 0.2 if (sections.get("projects") or projects) else 0
    exp_score = round(min(1.0, exp_part) * 20)

    stmts = max(impact["statements"], 1)
    q_ratio = impact["quantified"] / stmts
    imp_part = min(1.0, q_ratio / 0.3) * 0.6 + min(1.0, impact["strong_verbs"] / 6) * 0.4
    imp_part -= min(0.25, 0.06 * len(impact["weak_phrases"]))
    impact_score = round(max(0.0, min(1.0, imp_part)) * 15)

    struct = 0
    struct += 3 if contact["email"] else 0
    struct += 2 if contact["phone"] else 0
    struct += 2 if (contact["linkedin"] or contact["github"] or contact["portfolio"]) else 0
    struct += min(6, 2 * sum(1 for k in ("experience", "education", "skills") if sections.get(k)))
    struct += 2 if 250 <= words <= 900 else (1 if 150 <= words < 250 or 900 < words <= 1200 else 0)
    struct_score = min(15, struct)

    comp = 0
    comp += 2 if sections.get("summary") else 0
    comp += 3 if (sections.get("projects") or projects) else 0
    comp += 2 if (sections.get("certifications") or sections.get("achievements")) else 0
    comp += 3 if edu else 0
    comp_score = min(10, comp)

    score = skill_score + exp_score + impact_score + struct_score + comp_score
    if words < 35:  # almost empty resume can't score well
        score = min(score, 20)
    score = max(0, min(100, score))

    breakdown = [
        {"label": "Skill match", "score": skill_score, "max": 40},
        {"label": "Experience & projects", "score": exp_score, "max": 20},
        {"label": "Impact & wording", "score": impact_score, "max": 15},
        {"label": "Structure & ATS", "score": struct_score, "max": 15},
        {"label": "Completeness", "score": comp_score, "max": 10},
    ]

    # --- strengths --------------------------------------------------------
    strengths = []
    if matched:
        top = ", ".join(matched[:4])
        strengths.append(f"Your resume already shows {len(matched)} of {len(weights)} skills this role looks for, including {top}.")
    if years >= 1:
        strengths.append(f"About {years} year{'s' if years != 1 else ''} of dated experience was found ({_level(years).lower()}).")
    if impact["quantified"]:
        strengths.append(f"{impact['quantified']} achievement line{'s' if impact['quantified'] != 1 else ''} use numbers, e.g. \"{impact['quantified_examples'][0]}\"")
    if impact["strong_verbs"] >= 4:
        strengths.append(f"{impact['strong_verbs']} lines open with strong action verbs, which reads as ownership.")
    if contact["github"] or contact["portfolio"]:
        strengths.append("You link to code or a portfolio, which recruiters for this role value.")
    if edu:
        strengths.append(f"Education level detected: {edu}.")
    if projects:
        strengths.append(f"Projects are listed ({', '.join(projects[:2])}), showing hands-on practice.")
    if not strengths:
        strengths.append("There is little evidence to build on yet. The suggestions below show where to start.")

    # --- improvements (specific to this resume) ---------------------------
    improvements = []

    def add(priority, title, detail):
        improvements.append({"priority": priority, "title": title, "detail": detail})

    critical_missing = [s for s in missing if weights[s] == 3]
    if critical_missing:
        add("High", f"Add evidence of {', '.join(critical_missing[:3])}",
            f"These are core requirements for a {role_name}. If you have used them, name them in a bullet with what you built; if not, they are your first learning priority.")
    if not contact["email"]:
        add("High", "Add an email address", "Recruiters and ATS parsers look for contact details at the top of the resume.")
    if not contact["phone"]:
        add("Medium", "Add a phone number", "No phone number was detected.")
    if not (contact["linkedin"] or contact["github"] or contact["portfolio"]):
        add("Medium", "Link your professional profiles", "Add LinkedIn and, for technical roles, GitHub or a portfolio URL.")
    if impact["quantified"] == 0:
        add("High", "Quantify your achievements", "No numbers were found. Add results such as percentages, users, revenue, time saved or dataset sizes, e.g. 'Cut report time by 40%'.")
    elif q_ratio < 0.2:
        add("Medium", "Quantify more bullets", f"Only {impact['quantified']} of {impact['statements']} statements contain a number. Aim for roughly one in three.")
    if impact["weak_phrases"]:
        quoted = ", ".join(f"'{p}'" for p in impact["weak_phrases"][:3])
        ex = f" For example: \"{impact['weak_examples'][0]}\"" if impact["weak_examples"] else ""
        add("Medium", "Replace passive or filler wording", f"Found {quoted}. Start with a verb that shows ownership (built, led, reduced).{ex}")
    if impact["strong_verbs"] < 3 and impact["statements"] >= 3:
        add("Medium", "Start bullets with action verbs", "Few lines begin with verbs like Built, Led, Optimised or Delivered.")
    for key, label in (("experience", "work experience or internships"), ("education", "education"), ("skills", "a dedicated skills section")):
        if not sections.get(key) and not (key == "experience" and years):
            add("High" if key != "education" else "Low", f"Add a clear {key.title()} section", f"No heading for {label} was detected. ATS software relies on standard headings.")
    if not sections.get("projects") and not projects:
        add("Medium", "Add 2–3 relevant projects", f"Projects are the fastest way to show {role_name} skills when experience is limited.")
    if not sections.get("summary"):
        add("Low", "Add a 2–3 line summary", f"State your target ({user_goal}) and your strongest 2–3 skills up front.")
    if words < 200:
        add("High", "Resume is very short", f"Only about {words} words were found. Add detail on responsibilities, tools and outcomes.")
    elif words > 1100:
        add("Medium", "Resume is long", f"About {words} words. Trim to the most relevant 1–2 pages for this role.")
    if not improvements:
        add("Low", "Fine-tune for each application", "Mirror keywords from each job description to keep your match score high.")
    order = {"High": 0, "Medium": 1, "Low": 2}
    improvements.sort(key=lambda i: order[i["priority"]])

    # --- roadmap ----------------------------------------------------------
    roadmap_detailed = []
    bridge = matched[0] if matched else None
    for skill in missing[:7]:
        w = weights[skill]
        weeks = {3: 4, 2: 3, 1: 2}[w]
        idea = SKILL_PROJECTS.get(skill, f"build a small {role_name.lower()} project that uses {skill} and publish it")
        lead = f"Since you already use {bridge}, " if bridge and bridge != skill else ""
        action = f"{lead}learn {skill} basics, then {idea}."
        roadmap_detailed.append({
            "skill": skill,
            "priority": {3: "Critical", 2: "Important", 1: "Nice to have"}[w],
            "weeks": weeks,
            "action": action[0].upper() + action[1:],
        })
    roadmap = [f"{r['skill']} ({r['priority'].lower()}, ~{r['weeks']} wk): {r['action']}" for r in roadmap_detailed]

    # --- interview questions (grounded in the resume) ---------------------
    questions = []
    lead = [s for s in matched if SKILLS[s][0] not in ("Tools", "Soft Skills", "Process")] or matched
    lead.sort(key=lambda s: (-hits.get(s, 0), -weights[s]))
    if lead:
        questions.append(f"You list {lead[0]}. Describe a real problem you solved with it and what you would do differently now.")
    if len(lead) > 1:
        questions.append(f"How have you used {lead[0]} together with {lead[1]} in the same project?")
    if projects:
        questions.append(f"Tell me about \"{projects[0]}\": your role, the hardest technical decision and the outcome.")
    if impact["quantified_examples"]:
        questions.append(f"You mention \"{impact['quantified_examples'][0][:90]}\". How did you measure that result?")
    if years >= 3:
        questions.append("Tell me about a time you mentored someone or influenced a technical decision on your team.")
    elif years < 1:
        questions.append(f"You are early in your career. What have you built or learned independently that prepares you for {user_goal}?")
    questions.extend(role["questions"][:2 if len(questions) >= 4 else 3])
    if critical_missing:
        questions.append(f"This role needs {critical_missing[0]}, which is not on your resume. How would you get productive in it in your first month?")
    questions = questions[:8]

    # --- skill categories for charts -------------------------------------
    categories = {}
    for s in all_skills:
        categories.setdefault(SKILLS[s][0], []).append(s)
    skill_categories = [{"name": k, "count": len(v), "skills": v} for k, v in sorted(categories.items(), key=lambda kv: -len(kv[1]))]

    # --- summary ----------------------------------------------------------
    summary = (
        f"Compared with a typical {role_name} profile, this resume scores {score}/100 ({_verdict(score).lower()}). "
        f"It covers {len(matched)} of {len(weights)} role skills ({round(skill_ratio * 100)}% weighted match)"
    )
    summary += f" and shows about {years} year{'s' if years != 1 else ''} of experience." if years else " and shows no dated work experience."
    if critical_missing:
        summary += f" The biggest gap is {critical_missing[0]}."
    if not role_matched:
        summary += f" Your goal \"{user_goal}\" was not an exact known role, so the closest profile based on your resume ({role_name}) was used."

    ats_checks = [
        {"label": "Email address", "ok": contact["email"]},
        {"label": "Phone number", "ok": contact["phone"]},
        {"label": "LinkedIn / GitHub / portfolio", "ok": contact["linkedin"] or contact["github"] or contact["portfolio"]},
        {"label": "Experience section", "ok": bool(sections.get("experience") or years)},
        {"label": "Education section", "ok": bool(sections.get("education") or edu)},
        {"label": "Skills section", "ok": bool(sections.get("skills"))},
        {"label": "Projects section", "ok": bool(sections.get("projects") or projects)},
        {"label": "Measurable results", "ok": impact["quantified"] > 0},
        {"label": "Sensible length (250–900 words)", "ok": 250 <= words <= 900},
    ]

    return {
        "source": "local",
        "role": role_name,
        "role_recognized": role_matched,
        "goal": user_goal,
        "score": score,
        "verdict": _verdict(score),
        "match_percent": round(skill_ratio * 100),
        "summary": summary,
        "score_breakdown": breakdown,
        "stats": {
            "words": words,
            "years_experience": years,
            "level": _level(years),
            "education": edu or "Not detected",
            "bullets": impact["bullets"],
            "quantified": impact["quantified"],
            "action_verbs": impact["strong_verbs"],
        },
        "ats_checks": ats_checks,
        "strengths": strengths,
        "improvements": improvements,
        "skill_categories": skill_categories,
        "role_skills": [{"skill": s, "weight": weights[s], "found": s in hits} for s in sorted(weights, key=lambda s: (-weights[s], s))],
        "roadmap_detailed": roadmap_detailed,
        # keys kept for backward compatibility with older saved reports
        "skills": all_skills,
        "missing_skills": missing,
        "roadmap": roadmap,
        "interview_questions": questions,
    }


# --------------------------------------------------------------------------
# AI layer
# --------------------------------------------------------------------------
def _unique_strings(value, fallback):
    if not isinstance(value, list):
        return fallback
    out, seen = [], set()
    for item in value:
        if isinstance(item, str) and item.strip():
            item = item.strip()
            if item.casefold() not in seen:
                out.append(item)
                seen.add(item.casefold())
    return out


def _ai_enhance(local, resume_text, user_goal):
    facts = {
        "role_profile": local["role"],
        "score": local["score"],
        "skills_found": local["skills"],
        "missing_role_skills": local["missing_skills"],
        "stats": local["stats"],
    }
    prompt = f"""You are an experienced recruiter reviewing a resume for the target role "{user_goal}".
Facts already computed from the resume (trust them): {json.dumps(facts)}

Write advice that is specific to THIS resume: quote or refer to real content from it.
Do not give generic advice. Return ONLY a JSON object with keys:
- "summary": 2-3 sentence honest assessment.
- "strengths": array of 3-5 short strings.
- "improvements": array of 4-6 objects {{"priority": "High|Medium|Low", "title": str, "detail": str}}.
- "roadmap": array of objects {{"skill": str, "priority": "Critical|Important|Nice to have", "weeks": int, "action": str}} for the missing skills.
- "interview_questions": array of 6-8 questions tied to projects/companies/skills actually in the resume.

Resume:
\"\"\"
{resume_text[:12000]}
\"\"\"
"""
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.4,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "You are a precise, candid career advisor. Output valid JSON only."},
            {"role": "user", "content": prompt},
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("The AI returned an empty analysis.")
    start, end = content.find("{"), content.rfind("}") + 1
    if start < 0 or end <= start:
        raise ValueError("No JSON object found in the AI response.")
    data = json.loads(content[start:end])
    if not isinstance(data, dict):
        raise ValueError("The AI response must be a JSON object.")

    merged = dict(local)
    if isinstance(data.get("summary"), str) and data["summary"].strip():
        merged["summary"] = data["summary"].strip()
    merged["strengths"] = _unique_strings(data.get("strengths"), local["strengths"]) or local["strengths"]
    imps = []
    for i in data.get("improvements") or []:
        if isinstance(i, dict) and i.get("title"):
            pr = i.get("priority") if i.get("priority") in ("High", "Medium", "Low") else "Medium"
            imps.append({"priority": pr, "title": str(i["title"]), "detail": str(i.get("detail", ""))})
    if imps:
        merged["improvements"] = imps
    road = []
    for r in data.get("roadmap") or []:
        if isinstance(r, dict) and r.get("skill"):
            try:
                weeks = int(r.get("weeks", 3))
            except (TypeError, ValueError):
                weeks = 3
            road.append({"skill": str(r["skill"]), "priority": str(r.get("priority", "Important")),
                         "weeks": weeks, "action": str(r.get("action", ""))})
    if road:
        merged["roadmap_detailed"] = road
        merged["roadmap"] = [f"{r['skill']} (~{r['weeks']} wk): {r['action']}" for r in road]
    qs = _unique_strings(data.get("interview_questions"), local["interview_questions"])
    if qs:
        merged["interview_questions"] = qs
    merged["source"] = "ai"
    return merged


def analyze_resume(resume_text, user_goal):
    local = _build_local_analysis(resume_text, user_goal)
    if client is None:
        return local
    try:
        return _ai_enhance(local, resume_text, user_goal)
    except (OpenAIError, json.JSONDecodeError, IndexError, AttributeError, TypeError, ValueError, KeyError) as error:
        local["error"] = f"AI enhancement unavailable, showing the built-in analysis instead. ({error})"
        return local

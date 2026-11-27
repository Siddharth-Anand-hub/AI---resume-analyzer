# 🚀 AI Resume Analyzer

A Flask web app that scores a resume against a target role and gives feedback
specific to that resume: not generic, copy-paste advice.

## ✨ Features
- **Resume-driven scoring (0–100):** skill match, experience, impact, ATS structure and completeness
- **14 role profiles, 94 skills:** Backend, Frontend, Data Analyst, ML Engineer, DevOps, UX, and more
- **Skill-gap analysis** with weighted role requirements
- **Learning roadmap** with concrete project ideas and time estimates
- **Personalised interview questions** based on your own projects and skills
- **Dashboard:** score trend, top skills, most-missed skills, recent analyses
- **Report history:** search, reopen, delete, print or save as PDF
- **PDF / DOCX / TXT upload** or paste text
- **Optional OpenAI mode:** works fully offline without an API key

## 🛠 Tech Stack
Flask · SQLAlchemy · SQLite · PyPDF2 · python-docx · Waitress · OpenAI API (optional)

## ⚙️ Quick Start
    git clone <your-repo-url>
    cd AI_resume_analyser
    python -m venv .venv && .venv\Scripts\activate
    pip install -r requirements.txt
    python app.py        # http://localhost:5000

Optional environment variables: `SECRET_KEY`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `DATABASE_URL`

## 🔒 Security
Hashed passwords, CSRF protection, per-user report access, upload size limits.

## 🧪 Tests
    python -m unittest test_ai

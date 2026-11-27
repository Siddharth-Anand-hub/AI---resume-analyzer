# AI Resume Analyzer

A Flask web app that scores a resume against a target role and gives feedback that is specific to that resume.

## What's new
- **Resume-driven analysis.** Scores, skills, gaps, fixes, roadmap and interview questions are computed from the actual resume text (sections, contact info, experience years, quantified results, action verbs, filler phrases, 94 skills across 14 role profiles). Different resumes now produce different reports.
- **Works with or without OpenAI.** The built-in engine always runs. If `OPENAI_API_KEY` is set, the AI rewrites the summary, advice, roadmap and questions on top of those facts. If the API fails, the built-in result is shown with a notice.
- **Dashboard** with score trend, stats, most common skills, most missed skills and recent analyses.
- **Full report page** with score ring, score breakdown, ATS checklist, role-skill match, strengths, prioritised fixes, learning roadmap, interview questions, print/PDF.
- **History** with search, delete and links to every report. Old reports still open.
- **Security fixes:** hashed passwords (old plain-text passwords are upgraded on first login), CSRF protection, secret key from the environment, per-user report access, upload size limit.

## Run
```bash
python -m venv .venv
.venv\Scripts\activate          # Windows   (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
python app.py                   # http://localhost:5000
```

Optional environment variables:
```
SECRET_KEY=any-long-random-string     # keeps logins valid across restarts
OPENAI_API_KEY=sk-...                 # enables AI-enhanced mode
OPENAI_MODEL=gpt-4o-mini              # default
DATABASE_URL=sqlite:///ai_resume_analyser.db
```

The existing SQLite database is upgraded automatically on start (new `goal`, `score`, `created_at` columns).

## Structure
```
app.py          routes: auth, dashboard, analyze, report, history
ai.py           analysis engine (local scoring + optional OpenAI layer)
models.py db.py SQLAlchemy models and automatic schema upgrade
templates/      base, app_base (sidebar), dashboard, analyze, report, history, auth
static/style.css
test_ai.py      unit tests  ->  python -m unittest test_ai
```

## Adding roles or skills
Edit `ROLES` and `SKILLS` at the top of `ai.py`. Each role lists its skills with a weight (3 critical, 2 important, 1 nice to have).

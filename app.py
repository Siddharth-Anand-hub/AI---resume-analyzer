import json
import os
import secrets
from datetime import datetime
from functools import wraps

import PyPDF2
from docx import Document
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import models
import ai as ai_engine
from ai import ROLES, analyze_resume
from db import SessionLocal, ensure_schema

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB uploads

ensure_schema()


# ---------------------------------------------------------------- helpers
def get_db():
    """One DB session per request, closed automatically."""
    from flask import g
    if "db" not in g:
        g.db = SessionLocal()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    from flask import g
    db = g.pop("db", None)
    if db is not None:
        db.close()


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token
app.jinja_env.globals["role_names"] = list(ROLES)
app.jinja_env.globals["ai_enabled"] = lambda: ai_engine.client is not None


@app.before_request
def _check_csrf():
    if request.method == "POST":
        sent = request.form.get("_csrf", "")
        if not sent or not secrets.compare_digest(sent, session.get("_csrf", "")):
            abort(400, "Invalid or missing form token. Please go back, refresh the page and try again.")


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        user = get_db().get(models.User, session["user"])
        if not user:
            session.clear()
            return redirect(url_for("login"))
        return view(user, *args, **kwargs)

    return wrapper


def load_result(report):
    try:
        data = json.loads(report.result or "{}")
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def summarize(report):
    """Small dict used by the dashboard / history lists."""
    r = load_result(report)
    score = report.score if report.score is not None else r.get("score")
    return {
        "id": report.id,
        "goal": report.goal or r.get("goal") or "Resume analysis",
        "role": r.get("role", ""),
        "score": score,
        "verdict": r.get("verdict", ""),
        "match": r.get("match_percent"),
        "date": report.created_at,
        "skills": r.get("skills", []),
        "missing": r.get("missing_skills", []),
        "legacy": score is None,
    }


def score_class(score):
    if score is None:
        return "na"
    return "good" if score >= 70 else "mid" if score >= 45 else "low"


app.jinja_env.globals["score_class"] = score_class


@app.template_filter("fmt_date")
def fmt_date(value):
    return value.strftime("%d %b %Y, %H:%M") if value else "Earlier"


def extract_text(file):
    name = (file.filename or "").lower()
    if name.endswith(".pdf"):
        reader = PyPDF2.PdfReader(file)
        if reader.is_encrypted:
            raise ValueError("This PDF is password protected.")
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if name.endswith(".docx"):
        doc = Document(file)
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(parts)
    if name.endswith(".txt"):
        return file.read().decode("utf-8", errors="ignore")
    raise ValueError("Unsupported file type. Please upload a PDF, DOCX or TXT file.")


# ---------------------------------------------------------------- auth
@app.route("/")
def home():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        db = get_db()
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif db.query(models.User).filter_by(email=email).first():
            flash("An account with this email already exists.", "error")
        elif db.query(models.User).filter_by(username=username).first():
            flash("That username is taken. Please choose another.", "error")
        else:
            db.add(models.User(username=username, email=email, password=generate_password_hash(password)))
            db.commit()
            flash("Account created. Please log in.", "success")
            return redirect(url_for("login"))
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        db = get_db()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = db.query(models.User).filter_by(email=email).first()
        ok = False
        if user:
            stored = user.password or ""
            if stored.startswith(("scrypt:", "pbkdf2:")):
                ok = check_password_hash(stored, password)
            elif stored and secrets.compare_digest(stored, password):  # legacy plain-text row
                ok = True
                user.password = generate_password_hash(password)  # upgrade it
                db.commit()
        if ok:
            session.clear()
            session["user"] = user.id
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------- dashboard
@app.route("/dashboard")
@login_required
def dashboard(user):
    db = get_db()
    reports = (
        db.query(models.Report)
        .filter_by(user_id=user.id)
        .order_by(models.Report.id.asc())
        .all()
    )
    items = [summarize(r) for r in reports]
    scored = [i for i in items if i["score"] is not None]

    stats = {
        "total": len(items),
        "average": round(sum(i["score"] for i in scored) / len(scored)) if scored else None,
        "best": max((i["score"] for i in scored), default=None),
        "latest": scored[-1]["score"] if scored else None,
        "change": (scored[-1]["score"] - scored[0]["score"]) if len(scored) > 1 else None,
    }

    # trend chart points (last 10 scored analyses) as SVG coordinates
    trend = scored[-10:]
    width, height, pad = 520, 170, 24
    points = []
    for n, item in enumerate(trend):
        x = pad + (n * (width - 2 * pad) / (len(trend) - 1) if len(trend) > 1 else (width - 2 * pad) / 2)
        y = height - pad - (item["score"] / 100) * (height - 2 * pad)
        points.append({"x": round(x, 1), "y": round(y, 1), "score": item["score"], "label": item["goal"]})
    polyline = " ".join(f"{p['x']},{p['y']}" for p in points)

    def top(key):
        counts = {}
        for i in items:
            for s in i[key]:
                counts[s] = counts.get(s, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
        biggest = ranked[0][1] if ranked else 1
        return [{"name": n, "count": c, "pct": round(c / biggest * 100)} for n, c in ranked]

    latest_full = load_result(reports[-1]) if reports else None
    return render_template(
        "dashboard.html",
        user=user.username,
        stats=stats,
        recent=list(reversed(items))[:5],
        points=points,
        polyline=polyline,
        chart={"w": width, "h": height, "pad": pad},
        top_skills=top("skills"),
        top_missing=top("missing"),
        latest=latest_full if latest_full and latest_full.get("score") is not None else None,
        latest_id=reports[-1].id if reports else None,
        active="dashboard",
    )


# ---------------------------------------------------------------- analyze
@app.route("/analyze", methods=["GET", "POST"])
@login_required
def analyze(user):
    if request.method == "POST":
        goal = (request.form.get("goal") or "").strip()
        resume_text = (request.form.get("resume") or "").strip()
        file = request.files.get("file")
        if file and file.filename:
            try:
                resume_text = extract_text(file).strip()
            except Exception as exc:  # noqa: BLE001 - show any parse problem to the user
                flash(f"Could not read the file: {exc}", "error")
                return render_template("analyze.html", user=user.username, active="analyze", goal=goal, resume=request.form.get("resume", ""))
        if not goal:
            flash("Please enter the role you are targeting.", "error")
        elif len(resume_text) < 30:
            flash("The resume looks empty. Paste its text or upload a PDF/DOCX/TXT with readable text (scanned images are not supported).", "error")
        else:
            result = analyze_resume(resume_text, goal)
            report = models.Report(
                user_id=user.id,
                resume_text=resume_text,
                result=json.dumps(result),
                goal=goal,
                score=result.get("score"),
                created_at=datetime.utcnow(),
            )
            db = get_db()
            db.add(report)
            db.commit()
            return redirect(url_for("report", report_id=report.id))
        return render_template("analyze.html", user=user.username, active="analyze", goal=goal, resume=resume_text)
    return render_template("analyze.html", user=user.username, active="analyze", goal="", resume="")


# ---------------------------------------------------------------- reports
def _own_report(user, report_id):
    report = get_db().get(models.Report, report_id)
    if not report or report.user_id != user.id:
        abort(404)
    return report


@app.route("/report/<int:report_id>")
@login_required
def report(user, report_id):
    rep = _own_report(user, report_id)
    result = load_result(rep)
    legacy = result.get("score") is None
    return render_template(
        "report.html",
        user=user.username,
        report=rep,
        r=result,
        legacy=legacy,
        goal=rep.goal or result.get("goal") or "Resume analysis",
        active="history",
    )


@app.route("/report/<int:report_id>/delete", methods=["POST"])
@login_required
def delete_report(user, report_id):
    rep = _own_report(user, report_id)
    db = get_db()
    db.delete(rep)
    db.commit()
    flash("Report deleted.", "success")
    return redirect(url_for("history"))


@app.route("/history")
@login_required
def history(user):
    reports = (
        get_db().query(models.Report)
        .filter_by(user_id=user.id)
        .order_by(models.Report.id.desc())
        .all()
    )
    return render_template("history.html", user=user.username, items=[summarize(r) for r in reports], active="history")


@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(413)
def _error(err):
    messages = {413: "That file is too large (limit 5 MB)."}
    return render_template("error.html", code=err.code, message=messages.get(err.code, getattr(err, "description", "Something went wrong."))), err.code


if __name__ == "__main__":
    from waitress import serve

    print("Running on http://localhost:5000")
    serve(app, host="0.0.0.0", port=5000)

import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///ai_resume_analyser.db")
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# Columns added after the first version. Existing databases get them automatically.
_NEW_REPORT_COLUMNS = {
    "goal": "VARCHAR(200)",
    "score": "INTEGER",
    "created_at": "DATETIME",
}


def ensure_schema():
    """Create missing tables and add any new columns to an existing database."""
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    if "reports" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("reports")}
    with engine.begin() as conn:
        for name, ddl in _NEW_REPORT_COLUMNS.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE reports ADD COLUMN {name} {ddl}"))

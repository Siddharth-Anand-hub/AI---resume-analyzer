from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True)
    email = Column(String(100), unique=True)
    password = Column(String(255))  # werkzeug hash (older plain-text rows are upgraded on login)


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    resume_text = Column(Text)
    result = Column(Text)
    goal = Column(String(200))
    score = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

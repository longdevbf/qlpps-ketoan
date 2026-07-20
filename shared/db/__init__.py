"""Shared SQLAlchemy 2 base + engine + session.

Mọi app import:
    from shared.db import Base, get_db, engine

Models 4 schemas:
    class User(Base):
        __tablename__ = "users"
        __table_args__ = {"schema": "shared"}
"""
from .base import Base
from .session import engine, SessionLocal, get_db

__all__ = ["Base", "engine", "SessionLocal", "get_db"]

"""SQLite database setup.

The database file defaults to ``backend/foaming.db`` (relative to the repo
root when run from there). Override with FOAMING_DB_URL, e.g.
``sqlite:////tmp/foaming-test.db`` in tests.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DEFAULT_URL = "sqlite:///./backend/foaming.db"
DATABASE_URL = os.environ.get("FOAMING_DB_URL", DEFAULT_URL)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401  (register tables)

    Base.metadata.create_all(bind=engine)

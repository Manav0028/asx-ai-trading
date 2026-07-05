"""
Own engine/session factory — same Postgres server as storage/database.py
(shared instance, separate tables via journal/models.py's own Base), but a
completely independent migration lifecycle from the EOD system.
"""
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from journal.models import Base
from settings import DATABASE_URL

# SQLite (used for local/dev runs without a Postgres server) is served by
# SQLAlchemy's NullPool/SingletonThreadPool, which don't accept the
# QueuePool-only pool_size/max_overflow kwargs — only pass those for Postgres.
_engine_kwargs = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 10

engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db():
    Base.metadata.create_all(bind=engine)
    print("realtime_chart_ai: rtc_* tables created.")


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def health_check() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

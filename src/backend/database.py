"""
database.py — SQLite via SQLAlchemy, production-ready configuration.

Fixes applied:
  - Absolute path: DB always found regardless of working directory / CWD
  - WAL journal mode: eliminates "database is locked" under concurrent load
  - busy_timeout: readers wait 5 s before failing instead of erroring immediately
  - Connection pool tuned for FastAPI async concurrency
  - V3.1: Added Video and Slide tables for data model integrity
"""
import os
from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, event, Boolean, Float, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# ── Absolute path so DB is always found regardless of where uvicorn is started ─
_HERE         = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
_WORKSPACE    = os.path.join(_PROJECT_ROOT, "workspace")
os.makedirs(_WORKSPACE, exist_ok=True)

DATABASE_URL = f"sqlite:///{os.path.join(_WORKSPACE, 'chat_history.db')}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,   # Detect stale connections before handing them out
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _connection_record):
    """
    Apply WAL mode and performance pragmas on every new connection.
    WAL (Write-Ahead Logging): multiple readers can coexist with one writer —
    this is the fix for "database is locked" under concurrent FastAPI requests.
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")    # Core fix: concurrent access
    cursor.execute("PRAGMA synchronous=NORMAL")  # Faster writes, still crash-safe
    cursor.execute("PRAGMA busy_timeout=5000")   # Wait up to 5 s before "locked"
    cursor.execute("PRAGMA cache_size=-32000")   # 32 MB page cache
    cursor.execute("PRAGMA foreign_keys=ON")     # Enforce foreign key constraints
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ChatSession(Base):
    __tablename__ = "sessions"
    id         = Column(String,   primary_key=True, index=True)
    title      = Column(String,   default="New Chat")
    course     = Column(String,   default="All")
    created_at = Column(DateTime, default=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "messages"
    id         = Column(Integer,  primary_key=True, index=True)
    session_id = Column(String,   index=True)
    role       = Column(String)   # 'user' | 'assistant'
    content    = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Video and Slide entities (V3.1) ──────────────────────────────────────────

class Video(Base):
    __tablename__ = "videos"
    id          = Column(String, primary_key=True, index=True) # UUID
    filename    = Column(String)
    course      = Column(String, default="Unknown")
    status      = Column(String, default="pending") # pending, processing, completed, error
    progress    = Column(Integer, default=0) # percentage 0-100
    created_at  = Column(DateTime, default=datetime.utcnow)
    
    slides      = relationship("Slide", back_populates="video", cascade="all, delete-orphan")


class Slide(Base):
    __tablename__ = "slides"
    id            = Column(String, primary_key=True, index=True) # Global ID (e.g. Q_XXXX)
    video_id      = Column(String, ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    timestamp_ms  = Column(Float, default=0.0)
    ocr_text      = Column(Text)
    scenario      = Column(String, default="unknown")
    chroma_synced = Column(Boolean, default=False)
    created_at    = Column(DateTime, default=datetime.utcnow)
    
    # Optional image storage references (base64 string or file path)
    original_image = Column(Text, nullable=True)
    warped_image   = Column(Text, nullable=True)

    video = relationship("Video", back_populates="slides")


Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency — yields a DB session, always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

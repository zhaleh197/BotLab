from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, DateTime, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import DATABASE_URL

_kw = {"connect_args": {"check_same_thread": False}} if DATABASE_URL.startswith("sqlite") else {"pool_pre_ping": True}
engine = create_engine(DATABASE_URL, **_kw)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Bot(Base):
    __tablename__ = "bots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="بات جدید")
    template: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    platform: Mapped[str] = mapped_column(String(20), default="bale")  # bale | telegram
    token: Mapped[str] = mapped_column(String(200), default="")
    # Payment provider token from the platform's BotFather (Bale wallet / Telegram payments).
    payment_token: Mapped[str] = mapped_column(String(300), default="")
    bot_username: Mapped[str] = mapped_column(String(120), default="")
    webhook_secret: Mapped[str] = mapped_column(String(64), default="")
    live_version_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    agent_status: Mapped[str] = mapped_column(String(20), default="idle")  # idle | running | error
    requirements: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class BotVersion(Base):
    __tablename__ = "bot_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    spec: Mapped[dict] = mapped_column(JSON)
    tests: Mapped[list] = mapped_column(JSON, default=list)
    test_report: Mapped[dict] = mapped_column(JSON, default=dict)
    change_note: Mapped[str] = mapped_column(Text, default="")
    assumptions: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Message(Base):
    """Owner <-> agent conversation, plus 'step' rows that show the agent's work live."""
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | step
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class BotData(Base):
    """Runtime state of a bot (registrations, orders, per-user state). scope: live | sandbox."""
    __tablename__ = "bot_data"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    scope: Mapped[str] = mapped_column(String(20))
    data: Mapped[dict] = mapped_column(JSON, default=dict)


# Columns added after the first deploy: create_all() does not alter existing tables.
_ADDED_COLUMNS = {"bots": {"payment_token": "VARCHAR(300) DEFAULT ''"}}


def init_db():
    Base.metadata.create_all(engine)
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in _ADDED_COLUMNS.items():
            have = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols.items():
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))

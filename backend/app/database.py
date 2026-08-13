from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sqlite_columns(table: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {r[1] for r in rows}


def _sqlite_table_exists(table: str) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": table},
        ).fetchone()
    return row is not None


def _migrate_sqlite() -> None:
    """Add missing columns / rebuild incomplete Stage 3+ tables for local SQLite."""
    if not settings.database_url.startswith("sqlite"):
        return

    # Rebuild tables that may have been created incomplete during iterative development.
    rebuild = []
    if _sqlite_table_exists("cost_estimates") and "title" not in _sqlite_columns("cost_estimates"):
        rebuild.append("cost_estimates")
    if _sqlite_table_exists("sor_items") and "rate" not in _sqlite_columns("sor_items"):
        rebuild.append("sor_items")
    if _sqlite_table_exists("reports") and "report_type" not in _sqlite_columns("reports"):
        rebuild.append("reports")
    if _sqlite_table_exists("comparison_results") and "comparison_type" not in _sqlite_columns("comparison_results"):
        rebuild.append("comparison_results")
    if _sqlite_table_exists("notifications") and "is_read" not in _sqlite_columns("notifications"):
        rebuild.append("notifications")

    # Additive columns for CSI + bid mapping on existing BOQ items
    if _sqlite_table_exists("boq_items"):
        cols = _sqlite_columns("boq_items")
        alters: list[str] = []
        if "csi_code" not in cols:
            alters.append("ALTER TABLE boq_items ADD COLUMN csi_code VARCHAR(50)")
        if "bid_template_line_id" not in cols:
            alters.append("ALTER TABLE boq_items ADD COLUMN bid_template_line_id INTEGER")
        if "bid_match_confidence" not in cols:
            alters.append("ALTER TABLE boq_items ADD COLUMN bid_match_confidence NUMERIC(5,2)")
        if alters:
            with engine.begin() as conn:
                for stmt in alters:
                    conn.execute(text(stmt))

    if rebuild:
        with engine.begin() as conn:
            for table in rebuild:
                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
        Base.metadata.create_all(bind=engine)


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_sqlite()

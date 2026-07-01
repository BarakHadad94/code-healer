import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

# In local dev the DB sits at the project root.
# In Docker (DATA_DIR=/app/data) it lands in the mounted volume so it persists.
_default_dir = Path(__file__).resolve().parent.parent
_db_path = Path(os.environ.get("DATA_DIR", str(_default_dir))) / "code_healer.db"
DATABASE_URL = f"sqlite:///{_db_path}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)
    migrate_schema()


def migrate_schema() -> None:
    """Add columns to existing SQLite DBs without dropping data."""
    with engine.connect() as conn:
        cols = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(healing_runs)"))
        }
        if "activation_reason" not in cols:
            conn.execute(text(
                "ALTER TABLE healing_runs ADD COLUMN activation_reason VARCHAR"
            ))
            conn.commit()
        if "fix_branch" not in cols:
            conn.execute(text(
                "ALTER TABLE healing_runs ADD COLUMN fix_branch VARCHAR"
            ))
            conn.commit()
        if "input_tokens" not in cols:
            conn.execute(text("ALTER TABLE healing_runs ADD COLUMN input_tokens INTEGER"))
            conn.execute(text("ALTER TABLE healing_runs ADD COLUMN output_tokens INTEGER"))
            conn.execute(text("ALTER TABLE healing_runs ADD COLUMN estimated_cost_usd FLOAT"))
            conn.commit()

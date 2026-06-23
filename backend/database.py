from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# DB file lands at the project root (code-healer/code_healer.db)
DATABASE_URL = "sqlite:///./code_healer.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
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

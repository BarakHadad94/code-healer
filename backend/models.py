from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class HealingRun(Base):
    __tablename__ = "healing_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    repo: Mapped[str] = mapped_column(String)
    file_path: Mapped[str] = mapped_column(String)
    error_log: Mapped[str] = mapped_column(Text)
    fix_diff: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String)          # "running" | "success" | "failed" | "skipped"
    activation_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # "self_heal" | "deep_review" | "skipped"
    iterations: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fix_branch: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # local git branch holding the healed fix, e.g. "fix/code-healer-ab12cd34"
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

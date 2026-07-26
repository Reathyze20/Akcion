"""
Daily Action schemas — Path 1 of EFFICIENT_INVESTING_PLAYBOOK.md.

The contract for "Co mám dnes udělat?": at most 3 ranked, executable actions
with exact amounts, or the first-class rest state "Nic. Drž." Missing data is
surfaced in `warnings` — never silently rendered as a number.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ActionItem(BaseModel):
    """One executable instruction: what, how much, and why."""

    id: str
    ticker: str
    source_key: str  # GOMES | BREAKOUT_INVESTORS | COMBINED
    action_type: str  # TRIM | SELL_WAIT_TIME | SELL | BUY | LIQUIDATE_HEAVY
    current_price: float
    currency: str = "USD"
    target_price: float | None = None
    # Float, not int: T212/Degiro positions hold fractional shares.
    quantity: float
    estimated_czk_value: float
    reason: str
    urgency_score: int  # higher = do first
    review_required: bool = False  # dual-source CONFLICT — decide yourself


class DailyActionResponse(BaseModel):
    """The whole daily decision in one payload."""

    market_alert: str  # GREEN | YELLOW | ORANGE | RED | UNKNOWN
    available_cash_czk: float
    status: str  # "HOLD_HOLD_HOLD" ("Nic. Drž.") | "ACTION_REQUIRED"
    actions: list[ActionItem] = Field(default_factory=list, max_length=3)
    # Data gaps and stale inputs, in Czech, ready to render. Never empty
    # silently swallowed — an unlisted gap is a bug.
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)

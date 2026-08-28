"""
Daily Action schemas — Path 1 of EFFICIENT_INVESTING_PLAYBOOK.md.

The contract for "Co mám dnes udělat?": at most 3 ranked, executable actions
with exact amounts, or the first-class rest state "Nic. Drž." Missing data is
surfaced in `warnings` — never silently rendered as a number.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class ActionItem(BaseModel):
    """One executable instruction: what, how much, and why."""

    id: str
    ticker: str
    source_key: str  # GOMES | BREAKOUT_INVESTORS | COMBINED
    action_type: str  # TRIM | SELL_WAIT_TIME | SELL | BUY | LIQUIDATE_HEAVY | ROZPOR
    current_price: float
    currency: str = "USD"
    target_price: float | None = None
    # Float, not int: T212/Degiro positions hold fractional shares.
    quantity: float
    estimated_czk_value: float
    reason: str
    urgency_score: int  # higher = do first
    review_required: bool = False  # dual-source CONFLICT — decide yourself
    # Whose account this instruction is for. Two people use this app and their
    # holdings differ, so the same stock can be a trim for one and a hold for
    # the other — the weight it takes up is a fact about an account, not about
    # the company.
    portfolio_id: int | None = None
    owner: str | None = None

    # ------------------------------------------------------------------
    # The order, rather than the verdict.
    #
    # A verdict is only useful on a day the app gets opened, and that is the
    # one thing its owner cannot promise. A limit price can be placed at the
    # broker once and left sitting there. It is derived from the Green and Red
    # Lines rather than from today's quote, so it stays right while the price
    # moves — what a stale quote removes is only the app's ability to say
    # whether the order would fill today.
    # ------------------------------------------------------------------
    limit_price: float | None = None
    limit_currency: str | None = None
    #: The last day this instruction stands. After it the app has not looked at
    #: the company since, and an instruction nobody re-checked is not advice.
    valid_until: date | None = None
    #: What would make it wrong before then, in Czech, ready to render.
    invalidated_if: str = ""


class ConcentrationOut(BaseModel):
    """
    The portfolio-level reading from `app/services/concentration.py`, structured
    for the screen rather than folded into a sentence.

    Added 2026-08-25: the numbers already reached the user, but only as text
    inside `warnings` — true whenever a threshold was crossed, silent otherwise.
    A screen cannot show a trend from a sentence that only appears sometimes;
    this is the same reading, kept as numbers so a persistent tile can show it
    every day, above and below the threshold alike.
    """

    total_czk: float
    material_pct: float
    unassessed_pct: float
    #: The worst case: known-bad plus everything nobody can assess.
    upper_bound_pct: float
    material_tickers: list[str] = Field(default_factory=list)
    unassessed_tickers: list[str] = Field(default_factory=list)


class DailyActionResponse(BaseModel):
    """
    The whole daily decision in one payload.

    Computed per ACCOUNT. Until 2026-08-23 the engine read every portfolio as
    one pot: cash was summed across both and every position weight measured
    against the combined total. A holding worth 12 % of one account came out as
    6 % of the sum and passed a cap it should have failed, and one person's
    cash could fund a purchase offered to the other.
    """

    market_alert: str  # GREEN | YELLOW | ORANGE | RED | UNKNOWN
    available_cash_czk: float
    status: str  # "HOLD_HOLD_HOLD" ("Nic. Drž.") | "ACTION_REQUIRED"
    actions: list[ActionItem] = Field(default_factory=list)
    #: None when the reading could not be made (see `concentration_lookup`) or
    #: when no position had a knowable value — absent, not a reassuring zero.
    concentration: ConcentrationOut | None = None
    #: Every action the engine produced, ranked, WITHOUT the display cap.
    #:
    #: `actions` is capped at three on purpose — the daily list answers "what do
    #: I do today" and a list of nine is a list nobody reads. But the board
    #: shows one card per company and has to state each one's real stance:
    #: inheriting the cap made GSI.V read "DRŽ — dnes není důvod nic dělat"
    #: while the engine wanted it trimmed, which is silence dressed as a
    #: verdict. Consumers that show everything read this instead.
    all_actions: list[ActionItem] = Field(default_factory=list)
    # Data gaps and stale inputs, in Czech, ready to render. Never empty
    # silently swallowed — an unlisted gap is a bug.
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class OwnerActions(BaseModel):
    """One account's answer, with the person it belongs to named."""

    portfolio_id: int
    owner: str | None = None
    portfolio_name: str | None = None
    response: DailyActionResponse


class DailyActionsByOwner(BaseModel):
    """
    Every account, answered separately.

    Never a merged total. The whole reason this shape exists is that summing
    two accounts produces caps that are wrong for both of them, and a screen
    that shows one list cannot say whose turn it is to act.
    """

    market_alert: str
    sections: list[OwnerActions] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def anything_to_do(self) -> bool:
        return any(s.response.actions for s in self.sections)


# ==============================================================================
# The board — one card per company, for two people at once
# ==============================================================================

class OwnerLineOut(BaseModel):
    """What one person should do about one company."""

    owner: str
    portfolio_id: int
    #: Already Czech. Nobody reading this screen knows the enum.
    instruction_cs: str
    detail_cs: str
    action_type: str | None = None
    quantity: int | None = None
    limit_price: float | None = None
    limit_currency: str | None = None
    estimated_czk: float | None = None
    valid_until: datetime | None = None
    urgency: int = 0
    #: Share of THEIR account, never of both summed.
    weight_pct: float | None = None
    holds: bool = False


class BreakoutLineOut(BaseModel):
    """The second source, in one sentence."""

    stance: str = Field(description="SOUHLASI | NESOUHLASI | MLCI")
    summary_cs: str
    target: float | None = None
    endorsements: int = 0
    analyst: str | None = None
    verdict: str | None = None
    notes_cs: list[str] = Field(default_factory=list)


class SafetyLineOut(BaseModel):
    """How far the price can fall before something real stops it."""

    floor: float | None = None
    layer: str = Field("NONE", description="TANGIBLE_BOOK | NET_CASH | NONE")
    downside_pct: float | None = None
    upside_pct: float | None = None
    asymmetry: float | None = None
    below_floor: bool = False
    notes_cs: list[str] = Field(default_factory=list)


class BoardCardOut(BaseModel):
    """One company, everything both people need, in reading order."""

    ticker: str
    company_name: str | None = None
    band: str
    band_label_cs: str
    band_reason_cs: str
    rr_score: float | None = None
    deserved: float | None = None
    buy_below: float | None = None
    sell_above: float | None = None
    take_profit_above: float | None = None
    add_below: float | None = None
    line_currency: str | None = None
    trigger: str = "ZADNY"
    trigger_reason: str = ""
    quality_expired: bool = False
    breakout: BreakoutLineOut | None = None
    #: The downside, from the balance sheet — the one reading that measures
    #: which way the money can go against you. None when no floor is
    #: computable, which is not the same as no downside.
    safety: SafetyLineOut | None = None
    #: What the app can say about THIS company. On the card, not in a block
    #: above twelve of them where each line repeated its own card.
    notes_cs: list[str] = Field(default_factory=list)
    owners: list[OwnerLineOut] = Field(default_factory=list)
    urgency: int = 0


class BoardResponse(BaseModel):
    """The whole board, most urgent first."""

    generated_at: datetime
    cards: list[BoardCardOut] = Field(default_factory=list)
    #: Warnings that belong to the portfolio rather than to one company —
    #: the semafor, concentration, blind spots. Shown above the cards, because
    #: they change how every card below should be read.
    warnings: list[str] = Field(default_factory=list)
    market_alert: str | None = None

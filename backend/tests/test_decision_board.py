"""
One card per company, for two people at once.

    „Budu já a moje přítelkyně vědět, kdy do čeho investovat, co kdy prodat.
     Abychom prostě věděli."

Everything on the card already existed in pieces across three endpoints. What is
tested here is the joining, and mostly the two ways it can lie:

  * showing a contradiction as consensus — Breakout seeing 57 % of upside on a
    company Gomes calls PŘEPLACENO is the two of them disagreeing, and reading
    it as silence would put the wrong word on the card, and
  * leaving an owner's row blank — a blank reads as "the app has not looked at
    this", which for somebody opening the screen after three weeks away is the
    one impression that must never be wrong.
"""

from dataclasses import dataclass

from app.core.tickers import canonical_ticker
from app.services.breakout_band import WatchlistRow, build_view
from app.services.decision_board import (
    AGREE,
    DISAGREE,
    SILENT,
    _directional_stance,
    _owner_lines,
    _weight_pct,
)
from app.trading.gomes_logic import Band


@dataclass
class FakePortfolio:
    id: int
    owner: str
    name: str = ""
    cash_balance: float = 0.0


@dataclass
class FakePosition:
    ticker: str
    portfolio_id: int
    shares_count: float
    current_price: float
    currency: str = "USD"


@dataclass
class FakeAction:
    ticker: str
    action_type: str
    reason: str
    quantity: int = 0
    limit_price: float | None = None
    limit_currency: str | None = None
    estimated_czk_value: float = 0.0
    valid_until: object = None
    urgency_score: int = 0


TOM = FakePortfolio(id=1, owner="Tom", cash_balance=1808.0)
MISA = FakePortfolio(id=2, owner="Míša", cash_balance=0.0)


# ==============================================================================
# Do the two sources point the same way?
# ==============================================================================

def test_upside_on_a_cheap_band_is_agreement():
    assert _directional_stance(120.0, Band.NAKUP) == AGREE


def test_upside_on_an_expensive_band_is_disagreement():
    """
    The live case that exposed the first version. GSI.V is PŘEPLACENO and
    Breakout's target sits 57 % above the price — that is the two of them
    disagreeing, and calling it silence prints consensus over a contradiction.
    """
    assert _directional_stance(57.0, Band.PREPLACENO) == DISAGREE


def test_downside_on_a_cheap_band_is_disagreement():
    assert _directional_stance(-40.0, Band.POD_ZELENOU) == DISAGREE


def test_downside_on_an_expensive_band_is_agreement():
    assert _directional_stance(-40.0, Band.NAD_CERVENOU) == AGREE


def test_a_target_near_the_price_is_neither():
    assert _directional_stance(3.0, Band.NAKUP) == SILENT
    assert _directional_stance(-3.0, Band.NAKUP) == SILENT


def test_no_gomes_direction_means_nothing_to_agree_with():
    """
    Eight of twelve holdings are MIMO METODIKU. Breakout having a number there
    is worth showing and is not agreement with a band that does not exist.
    """
    assert _directional_stance(119.0, Band.MIMO_METODIKU) == SILENT
    assert _directional_stance(119.0, Band.NEZNAME) == SILENT


# ==============================================================================
# A named analyst outranks the arithmetic
# ==============================================================================

def test_a_written_verdict_is_recognised_as_a_stance():
    view = build_view(
        WatchlistRow(symbol="DFSC", implied_target=7.27, endorsements=2)
    )
    assert not view.verdict_is_bearish
    assert not view.verdict_is_bullish

    view.action_verdict = "SELL"
    assert view.verdict_is_bearish

    view.action_verdict = "BUY"
    assert view.verdict_is_bullish


def test_a_watch_verdict_is_neither_direction():
    """Robert Mock's DFSC note carried facts and no instruction."""
    view = build_view(WatchlistRow(symbol="DFSC", implied_target=7.27))
    view.action_verdict = "WATCH"
    assert not view.verdict_is_bearish
    assert not view.verdict_is_bullish


# ==============================================================================
# Every owner gets a row, including the one with nothing to do
# ==============================================================================

def test_an_owner_with_an_action_gets_the_instruction_in_czech():
    # Keyed canonically, exactly as the board keys it: GSI.V and GKPRF are one
    # company, and matching on the raw symbol silently finds nothing for every
    # dual-listed holding — four of the twelve.
    positions = [FakePosition("GSI.V", 1, 1000, 1.77, "CAD")]
    actions = {1: [FakeAction("GSI.V", "TRIM", "R/R pod zaslouženým", urgency_score=60)], 2: []}
    lines = _owner_lines(canonical_ticker("GSI.V"), [TOM, MISA], actions, positions)

    tom = next(o for o in lines if o.owner == "Tom")
    assert tom.instruction_cs == "ODEBRAT"
    assert tom.action_type == "TRIM"
    assert tom.urgency == 60


def test_no_raw_enum_reaches_the_screen():
    actions = {1: [FakeAction("X", "SELL_WAIT_TIME", "kapitál nepracuje")], 2: []}
    lines = _owner_lines("X", [TOM], actions, [])
    assert lines[0].instruction_cs == "PRODAT"
    assert "_" not in lines[0].instruction_cs


def test_an_owner_who_holds_and_has_nothing_to_do_is_told_so():
    """
    Not a blank. A blank reads as "the app has not looked at this", and after
    three weeks away that is the one impression that must never be wrong.
    """
    positions = [FakePosition("DAIO", 1, 500, 2.97)]
    lines = _owner_lines("DAIO", [TOM], {1: []}, positions)
    assert lines[0].instruction_cs == "DRŽ"
    assert lines[0].holds
    assert "není důvod nic dělat" in lines[0].detail_cs


def test_an_owner_who_does_not_hold_is_named_as_not_holding():
    lines = _owner_lines("DAIO", [MISA], {2: []}, [])
    assert lines[0].instruction_cs == "NEMÁ"
    assert not lines[0].holds


def test_both_owners_always_appear():
    positions = [FakePosition("DAIO", 1, 500, 2.97)]
    lines = _owner_lines("DAIO", [TOM, MISA], {1: [], 2: []}, positions)
    assert [o.owner for o in lines] == ["Tom", "Míša"]


def test_the_same_stock_can_tell_the_two_of_them_different_things():
    """
    The method working, not a contradiction: whoever bought earlier and cheaper
    takes profit sooner.
    """
    positions = [
        FakePosition("VTSI", 1, 1000, 3.13),
        FakePosition("VTSI", 2, 100, 3.13),
    ]
    actions = {1: [FakeAction("VTSI", "TRIM", "zdvojnásobení")], 2: []}
    lines = _owner_lines("VTSI", [TOM, MISA], actions, positions)

    assert [o.instruction_cs for o in lines] == ["ODEBRAT", "DRŽ"]


# ==============================================================================
# Weight is measured against the owner's own account
# ==============================================================================

def test_weight_is_a_share_of_the_owners_own_account():
    """
    Never of the two summed. A holding that is 12 % of her account reads as 6 %
    of the total and passes a cap it was meant to fail — that was a live bug.
    """
    positions = [
        FakePosition("DAIO", 2, 100, 12.0),   # 1200 in her account
        FakePosition("OTHER", 2, 100, 88.0),  # 8800 in her account
        FakePosition("BIG", 1, 10000, 100.0),  # a million in his
    ]
    hers = [p for p in positions if p.ticker == "DAIO"]
    assert _weight_pct(hers, MISA, positions) == 12.0


def test_cash_counts_towards_the_account_it_sits_in():
    positions = [FakePosition("DAIO", 1, 100, 9.0)]  # 900
    rich = FakePortfolio(id=1, owner="Tom", cash_balance=100.0)
    assert _weight_pct(positions, rich, positions) == 90.0


def test_an_unheld_position_has_no_weight():
    assert _weight_pct([], MISA, []) is None


def test_an_account_worth_nothing_does_not_divide_by_zero():
    positions = [FakePosition("DAIO", 3, 0, 0.0)]
    empty = FakePortfolio(id=3, owner="Nový účet", cash_balance=0.0)
    assert _weight_pct(positions, empty, positions) is None


def test_a_zero_share_row_in_a_funded_account_is_zero_percent_not_unknown():
    """Nought percent is a fact; None means the app could not work it out."""
    positions = [FakePosition("DAIO", 1, 0, 0.0)]
    assert _weight_pct(positions, TOM, positions) == 0.0

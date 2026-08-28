"""
Gold Mine is an absorbing stage, and a rough patch is not a demotion.

GOMES_VIDEO_ADDENDUM.md §V1. The one thing Gomes tells the viewer to write down
is this distinction:

    "The fact that you go through a rough patch -- less orders, the business
     slows down -- that does NOT mean you have shifted out of Gold Mine. You've
     already proven your product sells in the marketplace, so you're not going
     to go back to Wait Time."

Before this, both classifiers were memoryless, and `WAIT_TIME_SIGNALS` is
literally the vocabulary of a rough patch -- "delays", "missed guidance",
"lawsuit", "cfo left". A proven holding with one bad quarter was relabelled
WAIT_TIME, and the Buy Guard then refused to buy it at the exact moment it was
cheapest. That is the setup the whole method exists to catch, so these tests pin
both halves: the stage no longer moves backwards, AND the caution that used to
live in the stage now lives in the guard, where it names what is actually wrong.
"""

from datetime import datetime, timezone

from app.services.lifecycle_rubric import (
    GOLD_MINE,
    GREAT_FIND,
    WAIT_TIME,
    apply_ratchet,
)
from app.trading.gomes_logic import (
    GomesGatekeeper,
    LifecyclePhase,
    StockLifecycleClassifier,
)

#: Every phrase here is in `WAIT_TIME_SIGNALS`, and every one of them is
#: something a proven company says in a bad quarter.
ROUGH_PATCH_TEXT = (
    "ACME reported delays this quarter. ACME missed guidance and the cfo left "
    "ACME shortly afterwards."
)


# ==============================================================================
# The ratchet itself
# ==============================================================================

def test_wait_time_reading_on_a_proven_company_is_a_rough_patch_not_a_stage():
    got = apply_ratchet(WAIT_TIME, GOLD_MINE)
    assert got.phase == GOLD_MINE
    assert got.rough_patch is True
    assert got.held_back_cs  # the screen has to be able to say why


def test_the_stage_still_moves_forward():
    assert apply_ratchet(GOLD_MINE, WAIT_TIME).phase == GOLD_MINE
    assert apply_ratchet(WAIT_TIME, GREAT_FIND).phase == WAIT_TIME


def test_a_company_that_never_reached_anything_takes_the_reading():
    got = apply_ratchet(WAIT_TIME, None)
    assert got.phase == WAIT_TIME
    assert got.rough_patch is False


def test_silence_leaves_the_stage_alone():
    """
    No reading today is not a demotion. UNKNOWN is the absence of evidence and
    must never overwrite a stage that was reached and confirmed.
    """
    assert apply_ratchet(None, GOLD_MINE).phase == GOLD_MINE
    assert apply_ratchet("UNKNOWN", GOLD_MINE).phase == GOLD_MINE


def test_a_proven_company_is_not_demoted_to_great_find_either():
    """Backwards is backwards; only the Gold Mine case carries a rough patch."""
    got = apply_ratchet(GREAT_FIND, GOLD_MINE)
    assert got.phase == GOLD_MINE
    assert got.rough_patch is False
    assert got.changed


# ==============================================================================
# The keyword classifier, which is where the vocabulary problem lives
# ==============================================================================

def test_without_a_high_water_mark_the_keywords_still_say_wait_time():
    """
    The old behaviour, kept deliberately. A company nobody has ever placed in a
    stage has no proof of anything, so rough-patch vocabulary is all the
    evidence there is and Wait Time is the honest reading.
    """
    got = StockLifecycleClassifier.classify("ACME", ROUGH_PATCH_TEXT)
    assert got.phase is LifecyclePhase.WAIT_TIME
    assert got.rough_patch is False


def test_the_same_words_about_a_proven_company_do_not_demote_it():
    got = StockLifecycleClassifier.classify(
        "ACME", ROUGH_PATCH_TEXT, reached=LifecyclePhase.GOLD_MINE
    )
    assert got.phase is LifecyclePhase.GOLD_MINE
    assert got.rough_patch is True
    assert got.is_investable is True


def test_the_reason_survives_into_the_assessment():
    """A flag with no explanation behind it is a rumour, not a finding."""
    got = StockLifecycleClassifier.classify(
        "ACME", ROUGH_PATCH_TEXT, reached=LifecyclePhase.GOLD_MINE
    )
    assert "útlum" in got.reasoning


# ==============================================================================
# The counterweight: the caution moved, it did not disappear
# ==============================================================================

_PROVEN = dict(
    market_alert="GREEN",
    rr_score=8.0,
    deserved_score=4.0,
    cylinders=6,
    lifecycle_stage="GOLD_MINE",
)


def test_quality_agreed_before_the_slowdown_does_not_authorise_a_buy():
    """
    This gate is what stops §V1 from being a net loosening. Cylinders confirmed
    in May say nothing about a business that slowed in August.
    """
    allowed, gate, reason = GomesGatekeeper.check_buy_guard(
        **_PROVEN,
        rough_patch=True,
        rough_patch_since=datetime(2026, 8, 1, tzinfo=timezone.utc),
        cylinders_confirmed_at=datetime(2026, 5, 1),
    )
    assert allowed is False
    assert gate is GomesGatekeeper.BuyGate.ROUGH_PATCH_STALE_QUALITY
    assert "válc" in reason.lower()


def test_quality_re_agreed_after_the_slowdown_is_evidence_again():
    allowed, gate, _ = GomesGatekeeper.check_buy_guard(
        **_PROVEN,
        rough_patch=True,
        rough_patch_since=datetime(2026, 5, 1, tzinfo=timezone.utc),
        cylinders_confirmed_at=datetime(2026, 8, 1),
    )
    assert allowed is True
    assert gate is GomesGatekeeper.BuyGate.PASSED


def test_an_undated_rough_patch_refuses():
    """Consistent with every other missing input in this guard: it fails closed."""
    allowed, gate, _ = GomesGatekeeper.check_buy_guard(**_PROVEN, rough_patch=True)
    assert allowed is False
    assert gate is GomesGatekeeper.BuyGate.ROUGH_PATCH_STALE_QUALITY


def test_a_company_with_no_rough_patch_is_unaffected():
    allowed, gate, _ = GomesGatekeeper.check_buy_guard(**_PROVEN)
    assert allowed is True
    assert gate is GomesGatekeeper.BuyGate.PASSED


def test_aware_and_naive_timestamps_do_not_raise():
    """
    The lifecycle columns are TIMESTAMPTZ and the engine clock is naive. The
    first cylinder confirmation ever written once took `daily_actions` down
    this exact way; the guard must not repeat it.
    """
    GomesGatekeeper.check_buy_guard(
        **_PROVEN,
        rough_patch=True,
        rough_patch_since=datetime(2026, 5, 1, tzinfo=timezone.utc),
        cylinders_confirmed_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    GomesGatekeeper.check_buy_guard(
        **_PROVEN,
        rough_patch=True,
        rough_patch_since=datetime(2026, 5, 1),
        cylinders_confirmed_at=datetime(2026, 8, 1),
    )

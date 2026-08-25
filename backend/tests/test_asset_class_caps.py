"""
The one thing worth keeping out of `GomesLogicEngine`.

The tiers measure how sure a thesis is. They do not measure what happens if it
is wrong, and those are different questions: a biotech whose next readout
either doubles it or halves it is not an anchor however certain it feels.

What is tested is mostly the refusal. The engine this table came from defaulted
a missing asset class to HIGH_BETA_ROCKET — an unrecorded field quietly
becoming an 8 % ceiling on a risk profile nobody had assessed. On 2026-08-23
all twelve holdings are unclassified, so that default would have been doing all
the work.
"""

from app.services.asset_class_caps import (
    BASE_CAPS,
    apply_cap,
    cap_for,
    warning_cs,
)


# ==============================================================================
# The ceilings themselves
# ==============================================================================

def test_the_classes_are_ordered_by_how_badly_it_can_go():
    assert (
        BASE_CAPS["ANCHOR"]
        > BASE_CAPS["HIGH_BETA_ROCKET"]
        > BASE_CAPS["BIOTECH_BINARY"]
        > BASE_CAPS["TURNAROUND"]
        > BASE_CAPS["VALUE_TRAP"]
    )


def test_a_value_trap_is_capped_at_nothing():
    """The class means "do not own this", said in the same units as the rest."""
    assert cap_for("VALUE_TRAP") == 0.0


def test_the_class_is_read_however_it_was_typed():
    assert cap_for(" anchor ") == cap_for("ANCHOR") == 12.0


# ==============================================================================
# An absence is not a middle value
# ==============================================================================

def test_an_unrecorded_class_imposes_no_ceiling():
    """
    Not a default of 8 %. `GomesLogicEngine` defaulted the unknown to
    HIGH_BETA_ROCKET, which is a verdict about risk drawn from a blank field.
    """
    assert cap_for(None) is None
    assert cap_for("") is None


def test_a_class_nobody_recognises_imposes_no_ceiling():
    assert cap_for("SPACE_LASERS") is None


def test_no_ceiling_means_the_caller_keeps_what_it_had():
    """None must never be read as "no limit"."""
    assert apply_cap(2.0, None) == 2.0
    assert apply_cap(2.0, "SPACE_LASERS") == 2.0


# ==============================================================================
# Only ever downward
# ==============================================================================

def test_a_generous_class_cannot_unlock_a_tightened_position():
    """
    An anchor allows 12 %, but a tertiary tier already said 2 %. The smaller
    wins, so the order the limits are applied in cannot change the answer.
    """
    assert apply_cap(2.0, "ANCHOR") == 2.0


def test_a_strict_class_tightens_a_generous_tier():
    assert apply_cap(10.0, "BIOTECH_BINARY") == 3.0


def test_a_value_trap_closes_the_position_entirely():
    assert apply_cap(10.0, "VALUE_TRAP") == 0.0


def test_applying_it_twice_changes_nothing():
    once = apply_cap(10.0, "TURNAROUND")
    assert apply_cap(once, "TURNAROUND") == once


# ==============================================================================
# What reaches the screen
# ==============================================================================

def test_an_unclassified_company_is_named_not_ignored():
    warning = warning_cs("KUYA.V", None)
    assert warning is not None
    assert "nikdo nezaznamenal" in warning


def test_a_value_trap_says_so_in_words():
    assert "nekupuje" in warning_cs("XYZ", "VALUE_TRAP")


def test_a_normal_class_says_nothing():
    assert warning_cs("GSI.V", "ANCHOR") is None


def test_no_raw_enum_reaches_a_sentence():
    """Czech copy conventions: the screen never shows BIOTECH_BINARY."""
    warning = warning_cs("IMP.V", "VALUE_TRAP")
    assert "VALUE_TRAP" not in warning

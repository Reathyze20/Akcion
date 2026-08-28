"""
Numbers and dates as Czech writes them.

A screen that prints `4.23` and `3.6 %` beside `1 807,98 Kč` reads as machine
output, and machine output is what somebody stops trusting on the day its
advice is uncomfortable. These two people read every sentence this app shows
and neither reads English.
"""

from datetime import date, datetime

from app.core.czech import d, money, months, n, pct, plural


# ==============================================================================
# Decimal comma, and no grouping inside a sentence
# ==============================================================================

def test_a_number_uses_a_decimal_comma():
    assert n(4.23, 2) == "4,23"
    assert n(3.6) == "3,6"


def test_a_number_inside_a_sentence_is_not_grouped():
    """A space-separated group reads as two numbers mid-sentence."""
    assert n(1234.5) == "1234,5"


def test_places_are_respected():
    assert n(60.55, 0) == "61"
    assert n(60.55, 2) == "60,55"


def test_a_percentage_keeps_the_space_before_the_sign():
    assert pct(60.5) == "60,5 %"


# ==============================================================================
# Dates
# ==============================================================================

def test_a_date_drops_leading_zeros():
    """30. 6. 2026, not 30.06.2026."""
    assert d(date(2026, 6, 30)) == "30. 6. 2026"


def test_a_datetime_reads_the_same_as_a_date():
    assert d(datetime(2026, 6, 30, 14, 3)) == "30. 6. 2026"


def test_the_replace_shortcut_that_broke_dates_is_not_used():
    """
    The trap this module exists to avoid: replacing every "." with a "," across
    a finished sentence turned 30. 6. 2026 into 30, 6, 2026. Formatting happens
    where a number becomes text, never as a pass over prose.
    """
    sentence = f"hotovost vydrží {n(4.5)} měsíce (k {d(date(2026, 6, 30))})"
    assert "30. 6. 2026" in sentence
    assert "4,5" in sentence


# ==============================================================================
# Declension
# ==============================================================================

def test_czech_declines_one_a_few_and_many():
    assert plural(1, "měsíc", "měsíce", "měsíců") == "měsíc"
    assert plural(4, "měsíc", "měsíce", "měsíců") == "měsíce"
    assert plural(5, "měsíc", "měsíce", "měsíců") == "měsíců"
    assert plural(0, "měsíc", "měsíce", "měsíců") == "měsíců"


def test_a_fraction_takes_the_genitive():
    """„4,5 měsíce" — same form as five and up."""
    assert plural(4.5, "měsíc", "měsíce", "měsíců") == "měsíců"


def test_months_pairs_the_count_with_its_noun():
    assert months(1) == "1 měsíc"
    assert months(4) == "4 měsíce"
    assert months(8) == "8 měsíců"


# ==============================================================================
# Money never loses its currency
# ==============================================================================

def test_a_price_keeps_its_currency():
    """
    Four of twelve holdings trade in something other than dollars while their
    bands are quoted in dollars. An unlabelled number in a sentence about two
    currencies is the shape of the mistake that already cost one wrong call.
    """
    assert money(1.65, "CAD") == "1,65 CAD"


def test_a_price_without_a_currency_is_just_the_number():
    assert money(1.65) == "1,65"


def test_the_noun_agrees_with_the_number_the_reader_sees():
    """
    SMSI's runway is 4,4 months and prints as "4". Declining against 4,4 took
    the genitive and produced "4 měsíců" — a noun agreeing with a number
    nobody can see, which is precisely the machine-output tell this module
    exists to remove.
    """
    assert months(4.4) == "4 měsíce"
    assert months(4.6) == "5 měsíců"
    assert months(1.2) == "1 měsíc"
    assert months(0.6) == "1 měsíc"

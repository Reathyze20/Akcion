"""
How far the price can fall before something real stops it.

The app measures upside everywhere — R/R to the Red Line, Breakout's `upside`
ratio, the band. Not one of them says how much can be LOST. The Five Keys
framework, from the summary Gomes recommended, makes that the last question
before buying and puts it deliberately the other way round from a
discount-to-fair-value:

    "FKV's margin of safety is heavily conscious of what can go wrong, and not
     what the discount it is to fair value — the safety is thus purely based on
     the value of the assets."

Two things are tested hardest: that an absent floor never becomes a floor of
zero, and that the floor is made of things a liquidator could sell.
"""

from app.services.margin_of_safety import (
    DEBT_TO_CASH_RED_FLAG,
    GOOD_ASYMMETRY,
    IMPLAUSIBLE_ASYMMETRY,
    LAYER_NET_CASH,
    LAYER_NONE,
    LAYER_TANGIBLE,
    THIN_SUPPORT_PCT,
    Balance,
    read,
    support_level,
)

# VirTra as filed: equity 44,1 M, intangibles 0,57 M, 11,3 M shares — a
# tangible floor of 3,85 against a price of 3,13.
VTSI = Balance(
    cash=14_312_743, total_debt=7_541_839, equity=44_100_826,
    intangibles=569_762, shares=11_303_885,
)


# ==============================================================================
# The floor is made of things a liquidator could sell
# ==============================================================================

def test_goodwill_and_intangibles_are_taken_off():
    """
    They are the first entries written down when a thesis breaks, so a floor
    that counts them is not a floor.
    """
    with_goodwill = support_level(
        Balance(equity=10_000_000, goodwill=6_000_000, shares=1_000_000)
    )
    assert with_goodwill.floor_per_share == 4.0


def test_the_tangible_floor_wins_over_the_cash_one():
    support = support_level(VTSI)
    assert support.layer == LAYER_TANGIBLE
    assert round(support.floor_per_share, 2) == 3.85


def test_cash_alone_is_used_only_when_equity_is_missing_and_says_so():
    support = support_level(
        Balance(cash=5_000_000, total_debt=1_000_000, shares=1_000_000)
    )
    assert support.layer == LAYER_NET_CASH
    assert support.floor_per_share == 4.0
    assert any("jen z čisté hotovosti" in u for u in support.unknowns)


def test_debt_is_subtracted_from_the_cash_floor():
    """Cash somebody else has a claim on is not a floor under your shares."""
    support = support_level(
        Balance(cash=5_000_000, total_debt=4_000_000, shares=1_000_000)
    )
    assert support.net_cash_per_share == 1.0


def test_the_two_layers_are_not_added_together():
    """
    Tangible book already contains the cash. The book's example splits them for
    explanation; adding them would count the same money twice.
    """
    support = support_level(VTSI)
    assert support.floor_per_share == support.tangible_book_per_share
    assert support.floor_per_share != (
        (support.tangible_book_per_share or 0) + (support.net_cash_per_share or 0)
    )


# ==============================================================================
# An absent floor is not a floor of zero
# ==============================================================================

def test_no_balance_sheet_means_no_floor():
    support = support_level(Balance())
    assert support.layer == LAYER_NONE
    assert not support.known
    assert support.floor_per_share is None


def test_no_share_count_means_nothing_per_share():
    support = support_level(Balance(cash=5_000_000, equity=10_000_000))
    assert not support.known
    assert any("počet akcií" in u for u in support.unknowns)


def test_an_uncomputable_floor_says_it_is_not_the_same_as_no_risk():
    reading = read("XYZ", 10.0, Balance())
    [note] = reading.notes_cs()
    assert "nespočítám" in note
    assert "neznamená to, že tam žádná není" in note


def test_no_floor_produces_no_downside_number():
    """A missing number must never arrive as a comfortable one."""
    reading = read("XYZ", 10.0, Balance())
    assert reading.downside_pct is None
    assert reading.asymmetry is None


# ==============================================================================
# The reading
# ==============================================================================

def test_the_distance_to_the_floor_is_the_downside():
    reading = read("XYZ", 10.0, Balance(equity=5_000_000, shares=1_000_000))
    assert reading.downside_pct == 50.0


def test_a_price_below_the_floor_is_named_loudly():
    """
    VTSI as filed: 3,13 against a tangible floor of 3,85. Rare, and it means
    the market expects those assets not to survive — or knows something the
    balance sheet does not show.
    """
    reading = read("VTSI", 3.13, VTSI)
    assert reading.below_its_floor
    assert any("POD svou podlahou" in n for n in reading.notes_cs())


def test_thin_support_is_called_out():
    reading = read("XYZ", 10.0, Balance(equity=9_000_000, shares=1_000_000))
    assert reading.downside_pct is not None
    assert reading.downside_pct < THIN_SUPPORT_PCT
    assert any("dolů je blízko" in n for n in reading.notes_cs())


def test_the_asymmetry_needs_both_halves():
    floor_only = read("XYZ", 10.0, Balance(equity=5_000_000, shares=1_000_000))
    assert floor_only.asymmetry is None

    both = read("XYZ", 10.0, Balance(equity=5_000_000, shares=1_000_000), ceiling=25.0)
    assert both.asymmetry == 3.0


def test_a_good_asymmetry_is_described_as_such():
    # Floor at 5,00 under a price of 10,00 (50 % down) against a ceiling of
    # 30,00 (200 % up) — a ratio of 4, inside the band the framework calls good
    # and below the point where the ratio starts describing a doubtful input.
    reading = read("XYZ", 10.0, Balance(equity=5_000_000, shares=1_000_000), ceiling=30.0)
    assert reading.asymmetry is not None
    assert GOOD_ASYMMETRY <= reading.asymmetry < IMPLAUSIBLE_ASYMMETRY
    assert any("nahoru je toho víc" in n for n in reading.notes_cs())


def test_a_ceiling_below_the_price_is_not_upside():
    reading = read("XYZ", 30.0, Balance(equity=5_000_000, shares=1_000_000), ceiling=25.0)
    assert reading.upside_pct is None


# ==============================================================================
# "Having too much debt is a red flag"
# ==============================================================================

def test_debt_far_above_cash_is_flagged():
    support = support_level(
        Balance(cash=1_000_000, total_debt=5_000_000, equity=10_000_000, shares=1_000_000)
    )
    assert support.debt_heavy


def test_modest_debt_is_not_flagged():
    support = support_level(
        Balance(cash=5_000_000, total_debt=1_000_000, equity=10_000_000, shares=1_000_000)
    )
    assert not support.debt_heavy


def test_the_debt_flag_says_who_gets_paid_first():
    reading = read(
        "XYZ", 10.0,
        Balance(cash=1_000_000, total_debt=5_000_000, equity=8_000_000, shares=1_000_000),
    )
    assert any("dřív než ty" in n for n in reading.notes_cs())


def test_the_red_flag_threshold_is_a_multiple_not_a_sum():
    assert DEBT_TO_CASH_RED_FLAG > 1.0


# ==============================================================================
# The currency trap, in the half that measures upward
# ==============================================================================

def test_an_unconverted_ceiling_is_the_exchange_rate_wearing_a_percent_sign():
    """
    Live: IMP.V is priced at 0,62 EUR and its Red Line is 10,00 USD. Handing
    the raw ceiling over reported 1 513 % of upside and an asymmetry of 20 —
    a number made almost entirely of the euro-dollar rate.

    The reading itself is currency-blind on purpose: it divides what it is
    given. The caller reconciles, and this test pins the arithmetic that makes
    the mistake visible if the reconciliation is ever dropped.
    """
    raw = read("IMP.V", 0.62, Balance(cash=16_179_000, total_debt=2_318_000,
                                      shares=73_781_696), ceiling=10.00)
    converted = read("IMP.V", 0.62, Balance(cash=16_179_000, total_debt=2_318_000,
                                            shares=73_781_696), ceiling=8.60)

    assert raw.upside_pct is not None and raw.upside_pct > 1400
    assert converted.upside_pct is not None
    assert converted.upside_pct < raw.upside_pct


def test_the_floor_and_the_price_must_be_in_one_currency():
    """
    A euro price against a dollar floor understates the downside by the whole
    rate. Same defect as the ceiling, the other way round.
    """
    same = read("X", 1.00, Balance(equity=500_000, shares=1_000_000))
    assert same.downside_pct == 50.0


def test_an_extreme_ratio_points_at_the_input_not_at_the_opportunity():
    """
    IMP.V reads at 17: a Red Line of 10,00 USD against a price near 0,75 is a
    thirteen-bagger, which is an extraordinary claim about the ceiling rather
    than an extraordinary trade. The number is real; celebrating it would not be.
    """
    reading = read("IMP.V", 0.75, Balance(cash=16_179_000, total_debt=2_318_000,
                                          shares=73_781_696), ceiling=10.00)
    assert reading.asymmetry is not None
    assert reading.asymmetry >= IMPLAUSIBLE_ASYMMETRY
    assert any("nespolehlivý strop" in n for n in reading.notes_cs())


def test_a_merely_good_ratio_is_still_described_as_good():
    """The new flag must not swallow the case it was added beside."""
    reading = read("X", 10.0, Balance(equity=5_000_000, shares=1_000_000), ceiling=30.0)
    assert any("nahoru je toho víc" in n for n in reading.notes_cs())
    assert not any("nespolehlivý strop" in n for n in reading.notes_cs())

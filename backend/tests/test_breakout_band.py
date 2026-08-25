"""
Breakout's side of a company, and the two things it must never become.

The owner decided on 2026-08-23 that Breakout sits at the same level as Gomes —
equal in the right to PREVENT, not in the right to allow. `evaluate_dual_source_buy`
has implemented that from the day it was written and had never received a single
row: on 2026-08-24 no company in `stocks` carried `source_key =
BREAKOUT_INVESTORS`, so the veto was dead code.

Two failures are tested harder than anything else here:

  * a downloaded list becoming a bullish opinion — 28 unsigned rows would
    silently double the permitted size of 28 positions, and
  * a target without a floor becoming a band — the floor is the number the
    whole method rests on, and deriving one to complete the pair would
    manufacture it.
"""

from datetime import date, datetime, timedelta

from app.services.breakout_band import (
    TARGET_DISAGREEMENT_RATIO,
    THIN_ENDORSEMENT_COUNT,
    AnalystWord,
    WatchlistRow,
    build_view,
    compare_to_gomes,
    headroom_to_target,
)

SEEN = datetime(2026, 8, 30)


def listed(**kw) -> WatchlistRow:
    base = dict(
        symbol="DFSC", company_name="DEFSEC Technologies Inc.", endorsements=5,
        upside_ratio=3.6875, price_at_read=1.55, implied_target=7.2656,
    )
    base.update(kw)
    return WatchlistRow(**base)


def wrote(**kw) -> AnalystWord:
    base = dict(analyst="Robert Mock", said_on=date(2026, 8, 24))
    base.update(kw)
    return AnalystWord(**base)


# ==============================================================================
# A feed is not an opinion
# ==============================================================================

def test_the_downloaded_list_never_produces_a_verdict():
    """
    The failure this exists to prevent. Their API returns six fields and none
    of them is an author, so treating a row as bullish would double the
    permitted size of every name on the list on nobody's authority.
    """
    view = build_view(listed())
    assert view.action_verdict is None


def test_a_row_with_no_verdict_says_so_out_loud():
    view = build_view(listed())
    assert any("nikdo nepodepsal" in n for n in view.notes_cs)


def test_only_a_named_analyst_creates_a_verdict():
    view = build_view(listed(), [wrote(verdict="SELL")])
    assert view.action_verdict == "SELL"
    assert view.attributed_to == "Robert Mock"
    assert view.said_on == date(2026, 8, 24)


def test_a_thin_endorsement_count_is_named_as_one_persons_idea():
    view = build_view(listed(endorsements=2))
    assert any("nápad, ne stanovisko" in n for n in view.notes_cs)


def test_a_well_backed_name_gets_no_such_note():
    view = build_view(listed(endorsements=THIN_ENDORSEMENT_COUNT))
    assert not any("nápad, ne stanovisko" in n for n in view.notes_cs)


# ==============================================================================
# A target is not a band
# ==============================================================================

def test_a_target_with_no_floor_is_not_a_band():
    """
    Today's shape for all 28 names. The floor is the number the method rests
    on; deriving one to complete the pair would invent it.
    """
    view = build_view(listed())
    assert view.red_line == 7.2656
    assert view.green_line is None
    assert not view.has_band
    assert view.target_only


def test_the_missing_floor_is_stated_rather_than_filled_in():
    view = build_view(listed())
    assert any("pásmo z toho nedělám" in n for n in view.notes_cs)


def test_a_name_watched_being_added_gets_a_floor():
    """
    The read price only anchors anything if we saw the addition happen. For a
    name already on the list when polling began it is whatever it cost on an
    arbitrary Sunday.
    """
    view = build_view(listed(seen_added=True, first_seen_at=SEEN))
    assert view.green_line == 1.55
    assert view.has_band


def test_a_name_already_on_the_list_gets_no_floor_from_its_read_price():
    view = build_view(listed(seen_added=False))
    assert view.green_line is None


def test_a_price_an_analyst_named_beats_a_read_price():
    view = build_view(listed(seen_added=True), [wrote(buy_at=1.10)])
    assert view.green_line == 1.10
    assert view.has_band


# ==============================================================================
# One source may not vote twice
# ==============================================================================

def test_a_written_target_beats_a_derived_one():
    view = build_view(listed(), [wrote(target=4.00)])
    assert view.red_line == 4.00


def test_the_two_targets_disagreeing_is_shown_inside_one_source():
    """
    Not as two sources. A signed number and a ratio from the same community are
    one opinion stated twice, and counting them separately would let Breakout
    outvote Gomes on its own.
    """
    view = build_view(listed(), [wrote(target=4.00)])
    [note] = [n for n in view.notes_cs if "sám odporuje" in n]
    assert "Robert Mock" in note
    # Desetinná čárka: konvence projektu, a tenhle text čte člověk.
    assert "4,00" in note and "7,27" in note


def test_two_targets_that_broadly_agree_produce_no_argument():
    close = 7.2656 * (1 + TARGET_DISAGREEMENT_RATIO / 2)
    view = build_view(listed(), [wrote(target=close)])
    assert not any("sám odporuje" in n for n in view.notes_cs)


def test_the_most_recent_word_wins():
    view = build_view(listed(), [
        wrote(said_on=date(2026, 6, 1), target=3.00),
        wrote(said_on=date(2026, 8, 24), target=5.00),
    ])
    assert view.red_line == 5.00


# ==============================================================================
# Disagreement with Gomes is named, never averaged
# ==============================================================================

def test_a_lower_breakout_target_is_named():
    view = build_view(listed(), [wrote(target=9.00)])
    note = compare_to_gomes(view, gomes_red=15.50)
    assert "míň než Gomes" in note
    assert "12" not in note  # never the average of 9.00 and 15.50


def test_a_higher_breakout_target_still_defers_to_the_gomes_band():
    view = build_view(listed(), [wrote(target=108.24)])
    note = compare_to_gomes(view, gomes_red=60.00)
    assert "víc než Gomes" in note
    assert "hradí Gomesovo pásmo" in note


def test_no_gomes_line_means_nothing_to_compare():
    assert compare_to_gomes(build_view(listed()), gomes_red=None) is None


def test_no_breakout_target_means_nothing_to_compare():
    view = build_view(listed(implied_target=None, upside_ratio=None))
    assert compare_to_gomes(view, gomes_red=15.50) is None


# ==============================================================================
# Silence
# ==============================================================================

def test_a_company_they_do_not_cover_has_no_view():
    """
    Absent, not present-and-empty. An empty view reads as "they looked and had
    nothing", which is agreement by another name.
    """
    assert build_view(None) is None


def test_an_analyst_note_about_a_name_they_do_not_track_creates_no_view():
    assert build_view(None, [wrote(verdict="BUY")]) is None


# ==============================================================================
# The currency trap, which has already cost one wrong recommendation
# ==============================================================================

def fx(price, frm, to):
    """CZK-mediated, same shape as the engine's own converter."""
    rates = {"USD": 24.0, "CAD": 17.0, "EUR": 25.0, "CZK": 1.0}
    if frm not in rates or to not in rates:
        return None
    return price * rates[frm] / rates[to]


def no_rate(price, frm, to):
    return None


def test_a_dollar_price_needs_no_conversion():
    view = build_view(listed(implied_target=3.00))
    headroom, warning = headroom_to_target(view, 1.50, "USD", fx)
    assert headroom == 100.0
    assert warning is None


def test_a_canadian_price_is_converted_before_comparing():
    """
    GSI.V trades in Canadian dollars against a target quoted on the US listing.
    Comparing them raw is wrong by the whole exchange rate — the same defect
    that produced a TRIM at an R/R of 2.97 when the real figure was 4.23.
    """
    view = build_view(listed(symbol="GSI.V", implied_target=2.02))
    converted, _ = headroom_to_target(view, 1.77, "CAD", fx)
    raw, _ = headroom_to_target(view, 1.77, "USD", fx)
    assert converted != raw
    assert converted > raw  # CAD 1.77 is only USD 1.25, so more room, not less


def test_a_euro_price_is_converted_too():
    view = build_view(listed(symbol="KUYA.V", implied_target=1.89))
    headroom, warning = headroom_to_target(view, 0.459, "EUR", fx)
    assert warning is None
    assert headroom is not None


def test_no_rate_means_no_number_and_a_named_gap():
    """A number in the wrong money is worse than no number."""
    view = build_view(listed(symbol="GSI.V", implied_target=2.02))
    headroom, warning = headroom_to_target(view, 1.77, "CAD", no_rate)
    assert headroom is None
    assert "kurz nemám" in warning
    assert "o celý kurz" in warning


def test_no_target_means_nothing_to_measure_against():
    view = build_view(listed(implied_target=None, upside_ratio=None))
    assert headroom_to_target(view, 1.50, "USD", fx) == (None, None)


def test_no_price_means_nothing_to_measure():
    view = build_view(listed())
    assert headroom_to_target(view, None, "USD", fx) == (None, None)
    assert headroom_to_target(view, 0.0, "USD", fx) == (None, None)


def test_a_price_above_their_target_reads_as_negative_room():
    view = build_view(listed(implied_target=1.00))
    headroom, _ = headroom_to_target(view, 2.00, "USD", fx)
    assert headroom == -50.0

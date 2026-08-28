"""
„Sedí to k Markovi?" — the candidate screener.

Three properties are worth more here than any individual number, and each has a
failure mode that looks like success:

* **It never returns a verdict.** A summary score, or any word that reads as
  "buy", would be acted on — and the seven features are everything that is in
  the price, while Mark's actual reason for buying is not in the price at all.
* **It never counts what it could not compute.** A candidate with three usable
  features must not report "3 of 3 typical". The denominator has to be the
  truth, not the part that worked.
* **It never averages the neighbours.** Three nearest cases are an anecdote;
  "similar entries returned 34 % on average" is an anecdote with a decimal
  point, which is worse.

No network: the profile and the bars are both injected.
"""

import json
from datetime import date, timedelta

import pytest

from app.services.entry_features import Bar, Bars, to_bars
from app.services.gomes_fit import (
    CAVEAT_CS,
    FitError,
    Profile,
    ProfileEntry,
    Quantiles,
    fit_candidate,
    load_profile,
    render_cs,
)

#: Words that would turn a shape check into advice. The list is what the module
#: promises never to say; the test asserts the rendered output contains none.
FORBIDDEN = (
    "koupit", "kupte", "prodat", "prodej", "doporuč", "doporuc",
    "buy", "sell", "signál", "signal", "výhodn", "levné", "levná",
    "silný nákup", "příležitost",
)


def quantiles(median: float, spread: float = 10.0, n: int = 40) -> Quantiles:
    return Quantiles(
        n=n, minimum=median - 4 * spread, p10=median - 3 * spread,
        p25=median - spread, median=median, p75=median + spread,
        p90=median + 3 * spread, maximum=median + 4 * spread,
    )


def profile(*, n_rows: int = 40, neighbours: bool = True) -> Profile:
    entries = tuple(
        ProfileEntry(
            row_id=i, ticker=f"T{i:02d}", entry_date=f"2024-01-{i % 28 + 1:02d}",
            exit_date="2025-01-01", exit_kind="DECISION", exit_reason="RR_PRAVIDLO",
            note=f"poznamka {i}", sheet_return_pct=float(10 * i),
            features={
                "drawdown_from_52w_high_pct": -30.0 + i,
                "pct_of_52w_range": 50.0 + i,
                "ret_6m_pct": 40.0 + i,
                "vol_60d_annualised_pct": 80.0 + i,
                "median_dollar_volume_20d": 300_000.0 + i * 1000,
                "price_level": 6.0 + i * 0.1,
                "gauge_z_at_entry": 0.5 + i * 0.01,
            },
        )
        for i in range(n_rows)
    )
    return Profile(
        generated_at="2026-08-24",
        source="test",
        cohort={
            "n_rows": n_rows, "n_tickers": n_rows, "first_entry": "2021-01-07",
            "last_entry": "2026-08-13", "supports_neighbours": neighbours,
            "excluded": {},
        },
        features={
            "drawdown_from_52w_high_pct": quantiles(-26.0, 12.0),
            "pct_of_52w_range": quantiles(65.0, 22.0),
            "ret_6m_pct": quantiles(54.0, 48.0),
            "vol_60d_annualised_pct": quantiles(87.0, 28.0),
            "median_dollar_volume_20d": quantiles(330_000.0, 1_400_000.0),
            "price_level": quantiles(6.0, 4.8),
            "gauge_z_at_entry": quantiles(0.93, 0.2),
        },
        entries=entries,
    )


def bars(
    n: int = 400, price: float = 6.0, step: float = 0.0, volume: int = 60_000,
    ticker: str = "CAND",
) -> Bars:
    rows, day, value = [], date(2025, 1, 1), price
    while len(rows) < n:
        if day.weekday() < 5:
            rows.append(
                Bar(day=day, open=value, high=value * 1.03, low=value * 0.97,
                    close=value, adj_close=value, volume=volume)
            )
            value += step
        day += timedelta(days=1)
    return to_bars(ticker, rows)


# ==============================================================================
# It never gives advice
# ==============================================================================

class TestItNeverReturnsAVerdict:

    def test_no_word_in_the_output_can_be_read_as_a_recommendation(self):
        rendered = render_cs(
            fit_candidate("CAND", profile=profile(), bars=bars(), market_z=0.9)
        ).lower()
        found = [word for word in FORBIDDEN if word in rendered]
        assert found == [], f"nástroj radí: {found}"

    def test_there_is_no_summary_score(self):
        """
        Six buckets and three counts. No single number, because a single number
        gets read as a rating within a week of being printed.
        """
        result = fit_candidate("CAND", profile=profile(), bars=bars(), market_z=0.9)
        assert not hasattr(result, "score")
        assert not hasattr(result, "rating")
        assert not hasattr(result, "verdict")

    def test_the_caveat_is_always_rendered(self):
        rendered = render_cs(
            fit_candidate("CAND", profile=profile(), bars=bars(), market_z=0.9)
        )
        assert CAVEAT_CS in rendered
        assert "kontrola tvaru, ne teze" in rendered


# ==============================================================================
# The denominator is the truth
# ==============================================================================

class TestUncomputableIsNotCounted:

    def test_a_short_history_shrinks_the_numerator_and_says_so(self):
        """
        Three usable features must never report "3 of 3 typical".

        The count of buckets and the count of gaps have to add up to six, and
        the summary has to name what is missing.
        """
        short = bars(n=40)
        result = fit_candidate("CAND", profile=profile(), bars=short, market_z=0.9)

        assert len(result.uncomputable) > 0
        counted = (
            result.count("TYPICKE") + result.count("NA_OKRAJI") + result.count("MIMO")
        )
        assert counted + len(result.uncomputable) == 6
        assert "Nešlo spočítat" in result.summary_cs

    def test_a_full_history_leaves_nothing_uncomputed(self):
        result = fit_candidate("CAND", profile=profile(), bars=bars(), market_z=0.9)
        assert result.uncomputable == ()
        assert "Nešlo spočítat" not in result.summary_cs

    def test_a_missing_gauge_is_a_named_absence_not_a_zero(self):
        """
        "The market was neutral" and "I could not read the market" are different
        things, and only one of them is true when the index fetch fails.
        """
        result = fit_candidate("CAND", profile=profile(), bars=bars(), market_z=None)
        assert "nešlo spočítat" in result.gauge_note_cs
        assert "0.00" not in result.gauge_note_cs
        assert "+0" not in result.gauge_note_cs


# ==============================================================================
# Neighbours are cases, not evidence
# ==============================================================================

class TestNeighbours:

    def test_returns_are_never_averaged(self):
        """
        Each neighbour keeps its own number. An aggregate over three cases would
        be exactly the confident-number-from-nothing this codebase refuses.
        """
        result = fit_candidate("CAND", profile=profile(), bars=bars(), market_z=0.9)
        rendered = render_cs(result)

        # Every neighbour's own figure is there...
        for neighbour in result.neighbours:
            assert f"{neighbour.entry.sheet_return_pct:+.0f} %" in rendered

        # ...and there is no fourth figure standing for all of them. Counting
        # rather than grepping for "average": the wording could change, an
        # extra aggregated number could not hide.
        block = rendered.split("Tvarově nejblíž má k:")[1].split("(tři případy")[0]
        percentages = [
            token for token in block.split()
            if token.endswith("%") or token == "—"
        ]
        assert len(percentages) == len(result.neighbours)

    def test_they_are_labelled_as_anecdote(self):
        rendered = render_cs(
            fit_candidate("CAND", profile=profile(), bars=bars(), market_z=0.9)
        )
        assert "historka, ne důkaz" in rendered

    def test_a_thin_profile_shows_none_and_explains_why(self):
        """
        Below forty entries the three closest points are a coincidence with a
        distance metric, and the screen has to say that rather than go quiet.
        """
        thin = profile(n_rows=35, neighbours=False)
        result = fit_candidate("CAND", profile=thin, bars=bars(), market_z=0.9)
        assert result.neighbours == ()
        rendered = render_cs(result)
        assert "neukazují" in rendered
        assert "40 vstupech" in rendered

    def test_distances_are_shown(self):
        rendered = render_cs(
            fit_candidate("CAND", profile=profile(), bars=bars(), market_z=0.9)
        )
        assert "vzdálenost" in rendered


# ==============================================================================
# Buckets
# ==============================================================================

class TestBuckets:

    def test_the_middle_half_is_typical(self):
        q = quantiles(100.0, 10.0)
        assert q.bucket(100.0) == "TYPICKE"
        assert q.bucket(91.0) == "TYPICKE"
        assert q.bucket(109.0) == "TYPICKE"

    def test_the_tails_are_on_the_edge_then_outside(self):
        q = quantiles(100.0, 10.0)
        assert q.bucket(115.0) == "NA_OKRAJI"
        assert q.bucket(85.0) == "NA_OKRAJI"
        assert q.bucket(140.0) == "MIMO"
        assert q.bucket(60.0) == "MIMO"

    def test_no_percentile_number_is_printed(self):
        """
        "82nd percentile" off forty points claims precision the sample does not
        have. Buckets plus a raw count is what forty points support.
        """
        rendered = render_cs(
            fit_candidate("CAND", profile=profile(), bars=bars(), market_z=0.9)
        )
        assert "percentil" not in rendered.lower()
        assert " z 40 níž" in rendered


# ==============================================================================
# Refusals
# ==============================================================================

class TestRefusals:

    def test_no_bars_refuses_rather_than_rendering_six_cheerful_rows(self):
        with pytest.raises(FitError):
            fit_candidate("GONE", profile=profile(), bars=Bars(ticker="GONE"))

    def test_a_missing_profile_names_how_to_build_it(self, tmp_path):
        with pytest.raises(FitError, match="research.publish"):
            load_profile(tmp_path / "nothing.json")


# ==============================================================================
# The published artefact
# ==============================================================================

class TestThePublishedProfile:
    """
    The committed file the app actually reads. These pin what was published on
    2026-08-24 from forty reconciled entries.
    """

    @pytest.fixture(scope="class")
    def published(self) -> Profile:
        try:
            return load_profile()
        except FitError as exc:
            pytest.skip(f"{exc}")

    def test_it_carries_its_own_composition(self, published):
        """
        Without this the file reads as "Mark's rules" when it is a sample of
        forty, and that difference is the whole distance between a fact and a
        claim.
        """
        assert published.n_rows == 40
        assert published.n_tickers == 25
        assert published.cohort["excluded"]
        assert published.cohort["first_entry"] == "2021-01-07"

    def test_every_profile_feature_is_described(self, published):
        from app.services.entry_features import PROFILE_FEATURES
        for name in PROFILE_FEATURES:
            assert name in published.features
            assert published.features[name].n == 40
        assert "gauge_z_at_entry" in published.features

    def test_he_buys_after_a_rise_not_after_a_collapse(self, published):
        """
        The headline finding, pinned so it cannot drift out unnoticed.

        The median entry is 26 % below the 52-week high but in the UPPER half of
        the 52-week range and up 54 % over six months. That is a pullback inside
        an advance, not a broken-down value name — and the app's "buy near the
        green line" wording invites the second reading.
        """
        assert published.features["ret_6m_pct"].median > 25
        assert published.features["pct_of_52w_range"].median > 50
        assert -40 < published.features["drawdown_from_52w_high_pct"].median < -15

    def test_the_names_are_small_and_illiquid(self, published):
        assert published.features["price_level"].median < 15
        assert published.features["median_dollar_volume_20d"].median < 1_000_000

    def test_the_file_is_valid_json_and_readable_by_eye(self):
        from app.services.gomes_fit import PROFILE_PATH
        if not PROFILE_PATH.exists():
            pytest.skip("profil není publikovaný")
        raw = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        assert set(raw) == {"generated_at", "source", "cohort", "features", "entries"}
        assert len(raw["entries"]) == raw["cohort"]["n_rows"]

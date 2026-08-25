"""
Tests for the transcription of Mark Gomes' "Priority Ideas" sheet.

Two jobs, and they fail for different reasons.

The first half pins the real committed CSV: 231 rows, a known date span, every
row labelled, every `days` column agreeing with its own dates. These fail when
somebody edits the transcription — which is what you want, because it is
hand-typed from a PDF and every downstream artefact keys off its `row_id`.

The second half feeds the loader deliberately broken rows and checks it refuses
by name. That matters more than usual here: the whole dataset is one person's
reading of a scanned table, and a loader that quietly dropped what it could not
parse would turn a transcription error into a smaller sample nobody noticed.
"""

from datetime import date

import pytest

from research.dataset import (
    DAYS_TOLERANCE,
    ERA_MODERN,
    DatasetError,
    Entry,
    decided_exits,
    era_for,
    load_entries,
    reference_cohort,
)


@pytest.fixture(scope="module")
def entries() -> list[Entry]:
    return load_entries()


# ==============================================================================
# The committed sheet
# ==============================================================================

class TestTheRealSheet:
    """What is actually in data/priority_ideas.csv, pinned."""

    def test_row_count(self, entries):
        assert len(entries) == 231

    def test_date_span_matches_the_pdf(self, entries):
        opened = [e.initial_interest for e in entries]
        assert min(opened) == date(2014, 5, 8)   # Facebook, first row
        assert max(opened) == date(2026, 8, 13)  # CVD Equipment, last row

    def test_row_ids_are_unique_and_contiguous(self, entries):
        ids = [e.row_id for e in entries]
        assert len(set(ids)) == len(ids)
        assert sorted(ids) == list(range(1, 232))

    def test_rows_stay_in_pdf_order_not_date_order(self, entries):
        """
        Row 156 sits out of sequence in the source and is left there.

        Re-sorting would make `row_id` — the join key for every derived artefact
        and every exclusion reason — mean something other than "where this is in
        the PDF".
        """
        opened = [e.initial_interest for e in entries]
        assert opened != sorted(opened)

    def test_every_row_is_labelled(self, entries):
        assert all(e.instrument for e in entries)
        assert all(e.exit_kind for e in entries)

    def test_days_column_agrees_with_its_own_dates(self, entries):
        """
        The transcription check that carries the rest.

        A mistyped year or month moves `days` by 28 or more; the sheet's own
        arithmetic drifts by at most one. Nothing lands in between, so this
        catches the error class it is for without rejecting the sheet.
        """
        drift = {
            e.row_id: (e.days_claimed, e.days_actual)
            for e in entries
            if abs(e.days_claimed - e.days_actual) > DAYS_TOLERANCE
        }
        assert drift == {}

    def test_open_rows_count_their_days_to_the_sheet_date(self, entries):
        """Nine rows had no exit when the PDF was printed."""
        opens = [e for e in entries if e.is_open]
        assert len(opens) == 9
        assert {e.ticker for e in opens} == {
            "VTSI", "GEODF", "CXDO", "ITMSF", "GKPRF",
            "TPCS", "IZEA", "RDCM", "CVV",
        }

    def test_the_two_split_adjusted_rows_are_the_only_ones(self, entries):
        """
        NVDA and SMCI carry "Split Adj'd"; nothing else does.

        That is the whole of what the sheet says about price basis, and
        `prices.py` has to assume as-quoted for the other 229 rows.
        """
        adjusted = {e.ticker for e in entries if e.price_basis == "SPLIT_ADJUSTED"}
        assert adjusted == {"NVDA", "SMCI"}

    def test_the_duplicated_row_is_marked(self, entries):
        """
        Rows 156 and 186 are the same SMSI entry, transcribed twice.

        Both are kept, because the transcription is verbatim and the PDF really
        does say it twice. One is flagged so no cohort counts it as two.
        """
        by_id = {e.row_id: e for e in entries}
        assert by_id[156].duplicate_of == 186
        assert by_id[186].duplicate_of is None
        assert (by_id[156].ticker, by_id[156].initial_interest) == (
            by_id[186].ticker, by_id[186].initial_interest
        )
        assert len([e for e in entries if e.duplicate_of is not None]) == 1

    def test_the_peak_return_column_is_carried_as_text(self, entries):
        """
        It is split-contaminated beyond repair and must never be a number.

        MRIN reads 22394, GSAT 12850, BYND 5540 — those are reverse splits, not
        returns. The field name says so; this pins that the type does too.
        """
        assert all(isinstance(e.peak_return_live_pct_unusable, str) for e in entries)
        by_id = {e.row_id: e for e in entries}
        assert by_id[86].peak_return_live_pct_unusable == "22394"
        # The sheet also leaves an Excel error value in one cell.
        assert by_id[130].peak_return_live_pct_unusable == "#N/A"


# ==============================================================================
# Cohorts
# ==============================================================================

class TestCohorts:

    def test_era_boundaries(self):
        assert era_for(date(2016, 12, 31)) == "SHORT_BOOK_2014_2016"
        assert era_for(date(2017, 1, 1)) == "LONG_MICROCAP_2017_2018"
        assert era_for(date(2018, 12, 31)) == "LONG_MICROCAP_2017_2018"
        assert era_for(date(2019, 1, 1)) == "DAYTRADE_2019_2020"
        assert era_for(date(2020, 12, 31)) == "DAYTRADE_2019_2020"
        assert era_for(date(2021, 1, 1)) == ERA_MODERN

    def test_reference_cohort_size(self, entries):
        """
        The number this project's go/no-go gate is about.

        Fifty rows across thirty tickers. Pinned so a change to the cohort rule
        — or to one label — cannot silently shrink the sample the entry profile
        is built from.
        """
        cohort = reference_cohort(entries)
        assert len(cohort) == 50
        assert len({e.ticker for e in cohort}) == 30

    def test_reference_cohort_excludes_what_the_app_cannot_act_on(self, entries):
        cohort = reference_cohort(entries)
        assert all(e.instrument == "LONG_EQUITY" for e in cohort)
        assert all(e.era == ERA_MODERN for e in cohort)
        assert all(e.duplicate_of is None for e in cohort)

    def test_reference_cohort_keeps_open_positions(self, entries):
        """
        An entry is an entry whether or not we can see how it ended.

        Dropping the nine open rows would bias the profile towards whatever has
        had time to work, which is the opposite of what the profile is for.
        """
        assert sum(1 for e in reference_cohort(entries) if e.is_open) == 9

    def test_decided_exits_drop_sweeps(self, entries):
        """2016-04-25 closed eighteen positions. None of them is a decision."""
        decided = decided_exits(entries)
        assert all(e.exit_kind != "BATCH" for e in decided)
        assert not any(e.pause_interest == date(2016, 4, 25) for e in decided)

    def test_decided_exits_drop_bookmark_cleanups(self, entries):
        """
        A closed duplicate bookmark is not a sale — the position continues.

        This is the easier exclusion to miss, because those rows carry a
        real-looking exit date and a real-looking return. 2017-09-19 is four of
        them, which is why `batches.py` flags that date and it is still not a
        sweep.
        """
        decided = decided_exits(entries)
        assert all(e.exit_reason != "UKLID" for e in decided)
        assert not any(e.row_id in {4, 86, 100, 106} for e in decided)

    def test_the_most_common_stated_sell_reason_is_the_rr_rule(self, entries):
        """
        The finding this dataset gives up without any price data at all.

        Of the modern-era long exits that state a reason, the R/R rule is the
        commonest — which is what the app's trim logic assumes and had no
        evidence for until now. Pinned as a count, not a proportion: the
        denominator is fifteen, and "53 %" of fifteen overstates what that is.
        """
        modern = [
            e for e in decided_exits(entries)
            if e.era == ERA_MODERN
            and e.instrument == "LONG_EQUITY"
            and e.exit_reason != "UNKNOWN"
        ]
        assert len(modern) == 15
        assert [e.exit_reason for e in modern].count("RR_PRAVIDLO") == 8


# ==============================================================================
# What the loader refuses
# ==============================================================================

class TestRefusals:
    """
    Every refusal names the offending row.

    A loader that returned what it could parse would turn a typo into a smaller
    sample, and nobody would see it happen.
    """

    GOOD_SHEET = (
        "1,Acme,ACME,2024-01-01,2024-03-01,60,Long,CLOSED,1.00,2.00,100,100,N/A,,"
    )
    GOOD_LABEL = "1,ACME,LONG_EQUITY,DECISION,UNKNOWN,,"

    def _load(self, tmp_path, monkeypatch, sheet_rows, label_rows):
        import research.dataset as ds

        sheet = tmp_path / "sheet.csv"
        labels = tmp_path / "labels.csv"
        sheet.write_text(
            "row_id,company,ticker,initial_interest,pause_interest,days,"
            "inclination,status,initial_price,final_price,final_change_pct,"
            "final_net_change_pct,peak_return_live_pct,latest_notes,footnote\n"
            + "\n".join(sheet_rows) + "\n",
            encoding="utf-8",
        )
        labels.write_text(
            "row_id,ticker,instrument,exit_kind,exit_reason,duplicate_of,"
            "label_note\n" + "\n".join(label_rows) + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(ds, "SHEET_CSV", sheet)
        monkeypatch.setattr(ds, "LABELS_CSV", labels)
        return ds.load_entries()

    def test_a_good_pair_loads(self, tmp_path, monkeypatch):
        loaded = self._load(tmp_path, monkeypatch, [self.GOOD_SHEET], [self.GOOD_LABEL])
        assert [e.row_id for e in loaded] == [1]

    def test_label_without_a_row(self, tmp_path, monkeypatch):
        with pytest.raises(DatasetError, match="2"):
            self._load(
                tmp_path, monkeypatch,
                [self.GOOD_SHEET],
                [self.GOOD_LABEL, "2,GHOST,LONG_EQUITY,DECISION,UNKNOWN,,"],
            )

    def test_row_without_a_label(self, tmp_path, monkeypatch):
        with pytest.raises(DatasetError, match="2"):
            self._load(
                tmp_path, monkeypatch,
                [
                    self.GOOD_SHEET,
                    "2,Beta,BETA,2024-01-01,2024-03-01,60,Long,CLOSED,1,2,"
                    "100,100,N/A,,",
                ],
                [self.GOOD_LABEL],
            )

    def test_exit_before_entry(self, tmp_path, monkeypatch):
        with pytest.raises(DatasetError, match="initial_interest"):
            self._load(
                tmp_path, monkeypatch,
                [
                    "1,Acme,ACME,2024-03-01,2024-01-01,-60,Long,CLOSED,1,2,"
                    "100,100,N/A,,"
                ],
                [self.GOOD_LABEL],
            )

    def test_days_off_by_a_mistyped_year(self, tmp_path, monkeypatch):
        with pytest.raises(DatasetError, match="425"):
            self._load(
                tmp_path, monkeypatch,
                [
                    "1,Acme,ACME,2024-01-01,2024-03-01,425,Long,CLOSED,1,2,"
                    "100,100,N/A,,"
                ],
                [self.GOOD_LABEL],
            )

    def test_days_off_by_one_is_tolerated(self, tmp_path, monkeypatch):
        """The sheet's own arithmetic drifts. Correct transcription of it passes."""
        loaded = self._load(
            tmp_path, monkeypatch,
            ["1,Acme,ACME,2024-01-01,2024-03-01,61,Long,CLOSED,1,2,100,100,N/A,,"],
            [self.GOOD_LABEL],
        )
        assert loaded[0].days_claimed == 61

    def test_unknown_inclination(self, tmp_path, monkeypatch):
        with pytest.raises(DatasetError, match="inclination"):
            self._load(
                tmp_path, monkeypatch,
                [
                    "1,Acme,ACME,2024-01-01,2024-03-01,60,Sideways,CLOSED,1,2,"
                    "100,100,N/A,,"
                ],
                [self.GOOD_LABEL],
            )

    def test_unknown_instrument(self, tmp_path, monkeypatch):
        with pytest.raises(DatasetError, match="instrument"):
            self._load(
                tmp_path, monkeypatch, [self.GOOD_SHEET],
                ["1,ACME,CRYPTO,DECISION,UNKNOWN,,"],
            )

    def test_ticker_disagreement_between_the_two_files(self, tmp_path, monkeypatch):
        """The join key is row_id, so a mismatched ticker is a silent mis-label."""
        with pytest.raises(DatasetError, match="ticker"):
            self._load(
                tmp_path, monkeypatch, [self.GOOD_SHEET],
                ["1,OTHER,LONG_EQUITY,DECISION,UNKNOWN,,"],
            )

    def test_closed_row_with_no_exit_date(self, tmp_path, monkeypatch):
        """The sheet contradicting itself is surfaced, never guessed at."""
        with pytest.raises(DatasetError, match="CLOSED"):
            self._load(
                tmp_path, monkeypatch,
                ["1,Acme,ACME,2024-01-01,,967,Long,CLOSED,1,2,100,100,N/A,,"],
                ["1,ACME,LONG_EQUITY,STILL_OPEN,,,"],
            )

    def test_open_row_carrying_an_exit_reason(self, tmp_path, monkeypatch):
        with pytest.raises(DatasetError, match="exit_reason"):
            self._load(
                tmp_path, monkeypatch,
                ["1,Acme,ACME,2024-01-01,,967,Long,,1,2,100,100,N/A,,"],
                ["1,ACME,LONG_EQUITY,STILL_OPEN,RR_PRAVIDLO,,"],
            )

    def test_zero_entry_price(self, tmp_path, monkeypatch):
        with pytest.raises(DatasetError, match="initial_price"):
            self._load(
                tmp_path, monkeypatch,
                ["1,Acme,ACME,2024-01-01,2024-03-01,60,Long,CLOSED,0,2,100,100,N/A,,"],
                [self.GOOD_LABEL],
            )

    def test_zero_exit_price_is_allowed(self, tmp_path, monkeypatch):
        """An option that expired worthless really did settle at zero."""
        loaded = self._load(
            tmp_path, monkeypatch,
            [
                "1,Acme puts,ACME,2024-01-01,2024-03-01,60,Write,CLOSED,0.40,"
                "0.00,-100,100,N/A,,"
            ],
            ["1,ACME,OPTION,DECISION,RR_PRAVIDLO,,"],
        )
        assert loaded[0].final_price == 0.0

    def test_duplicate_pointing_at_nothing(self, tmp_path, monkeypatch):
        with pytest.raises(DatasetError, match="99"):
            self._load(
                tmp_path, monkeypatch, [self.GOOD_SHEET],
                ["1,ACME,LONG_EQUITY,DECISION,UNKNOWN,99,"],
            )

    def test_every_fault_is_reported_not_just_the_first(self, tmp_path, monkeypatch):
        """
        231 rows means one-fault-per-run is one fix per run. The refusal has to
        be a work list, not a doorbell.
        """
        with pytest.raises(DatasetError) as caught:
            self._load(
                tmp_path, monkeypatch,
                [
                    "1,Acme,ACME,2024-01-01,2024-03-01,60,Sideways,CLOSED,0,2,"
                    "100,100,N/A,,",
                    "2,Beta,BETA,2024-01-01,2024-03-01,999,Long,CLOSED,1,2,"
                    "100,100,N/A,,",
                ],
                [
                    "1,ACME,LONG_EQUITY,DECISION,UNKNOWN,,",
                    "2,BETA,LONG_EQUITY,DECISION,UNKNOWN,,",
                ],
            )
        message = str(caught.value)
        assert "1" in message and "2" in message
        assert "3" in message.split("\n")[0]  # three faults counted in the header


# ==============================================================================
# The batch proposal
# ==============================================================================

class TestBatchProposals:

    def test_every_candidate_row_was_looked_at(self, entries):
        """
        `batches.py` proposes, the labels file rules. What must never happen is a
        flagged row that is neither marked BATCH nor explained — that is a
        cleaning pass somebody abandoned halfway.
        """
        from research.batches import unexplained
        assert unexplained(entries) == []

    def test_the_known_sweeps_are_all_flagged(self, entries):
        from research.batches import propose
        dates = {c.exit_date for c in propose(entries)}
        for known in (
            date(2015, 6, 10), date(2015, 6, 22), date(2016, 4, 25),
            date(2017, 10, 11), date(2025, 1, 3),
        ):
            assert known in dates

    def test_the_biggest_sweep_is_the_one_from_2016(self, entries):
        from research.batches import propose
        biggest = max(propose(entries), key=lambda c: len(c.rows))
        assert biggest.exit_date == date(2016, 4, 25)
        assert len(biggest.rows) == 18
        assert biggest.exceptions == ()

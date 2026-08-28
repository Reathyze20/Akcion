"""
Mark Gomes' "Priority Ideas" sheet, loaded and checked.

Two files, joined on `row_id`:

* `data/priority_ideas.csv`        — verbatim transcription of the PDF
* `data/priority_ideas_labels.csv` — human judgement about each row

They are separate so the transcription can be diffed against the PDF without
anybody's opinion mixed into it, and so a label can be corrected without
touching the evidence. Same split the app makes between a proposal and a
confirmation (see `scripts/propose_cylinders.py`).

`load_entries()` refuses rather than returns a partial list. Every refusal names
every offending `row_id` — one at a time would mean one fix per run over 231
rows, and the point of the check is to make a transcription pass finite.

What this module will NOT do
---------------------------
Repair the sheet. Where the sheet contradicts itself (`days` off by one against
its own dates, a note dated a year after the exit it sits on, the same entry
transcribed twice) the contradiction is recorded and surfaced, never smoothed
over. A cleaned dataset that no longer matches the PDF is a dataset nobody can
check.
"""

from __future__ import annotations

import csv
import pathlib
from dataclasses import dataclass
from datetime import date
from typing import Final, Iterable, Iterator

DATA: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parent / "data"
SHEET_CSV: Final[pathlib.Path] = DATA / "priority_ideas.csv"
LABELS_CSV: Final[pathlib.Path] = DATA / "priority_ideas_labels.csv"

#: The date printed in the PDF's header. Open rows count their `days` to this
#: day, so it is what an open row's duration is checked against.
SHEET_DATE: Final[date] = date(2026, 8, 24)

#: How far the sheet's own `days` column may differ from the difference of its
#: own dates before the row is refused.
#:
#: Not zero, and the reason matters. Spot-checking shows the sheet's arithmetic
#: is itself off by one on a run of rows closed in 2016 (GLUU 5/8/2014 ->
#: 4/25/2016 says 719 where the dates give 718; AERO, KING and BKS do the same),
#: while other rows are exact to the day. So a tolerance of zero would reject
#: correct transcription of an incorrect sheet.
#:
#: What the check is actually for is the transcription error that matters: a
#: mistyped year or month, which moves `days` by 28 or more. Two is comfortably
#: below that and comfortably above the sheet's own drift.
DAYS_TOLERANCE: Final[int] = 2

INSTRUMENTS: Final[frozenset[str]] = frozenset(
    {"LONG_EQUITY", "SHORT_EQUITY", "ETF_HEDGE", "OPTION", "BASKET"}
)
EXIT_KINDS: Final[frozenset[str]] = frozenset(
    {"DECISION", "BATCH", "STILL_OPEN", "DELISTED", "ACQUIRED", "UNKNOWN"}
)
EXIT_REASONS: Final[frozenset[str]] = frozenset(
    {
        "RR_PRAVIDLO",
        "ALERT",
        "TEZE_SE_ZLOMILA",
        "GRADUACE",
        "AKVIZICE",
        "WAIT_TIME",
        "ZTRATA_ZAJMU",
        "UKLID",
        "UNKNOWN",
    }
)
#: Every value the sheet's own Inclination column takes. Listed so a typo in
#: transcription cannot pass as a sixth kind of position.
INCLINATIONS: Final[frozenset[str]] = frozenset(
    {"Long", "Short", "Write", "Bearish", "Short (Bullish)"}
)

#: Footnote texts from page 6 of the PDF, by the marker used in the table.
#: Only [8] and [9] carry information the price reconciliation needs.
FOOTNOTES: Final[dict[str, str]] = {
    "[1]": "Prior note: Hit a nasty speed bump. May be dead unitl spring... wait?",
    "[2]": "https://seekingalpha.com/instablog/84364-mark-gomes/5025628-portfolio-update-earnings-earnings-earnings",
    "[3]": 'Read "Tactile Systems: Catalysts For 75% Downside" on SA.',
    "[4]": "https://www.statista.com/statistics/199359/market-share-of-wireless-carriers-in-the-us-by-subscriptions/",
    "[5]": "10/30: Management update coming. With the stock back under $10, I'm anxious to nail down its fair valuation.",
    "[6]": "Sold the Jan 12.50 and 17.50 puts (mostly the 12.50s).",
    "[7]": "Adjusted to reflect the average value / ROI on the Jan puts that were written (a.k.a. shorted).",
    "[8]": "Split Adj'd",
    "[9]": "Split Adj'd.",
}

#: Markers that say the price in that row is already split-adjusted. Everything
#: else in the sheet is as-quoted on the day, which is what the reconciliation
#: in `prices.py` has to assume.
SPLIT_ADJUSTED_MARKERS: Final[frozenset[str]] = frozenset({"[8]", "[9]"})


# ==============================================================================
# Eras
# ==============================================================================

#: Which method was running when the position was opened.
#:
#: Derived from `initial_interest`, not hand-labelled, because the boundaries
#: below turned out to be clean date cuts and 231 hand-typed values would only
#: add a way to be wrong. The judgement is in choosing the boundaries, and it is
#: written down here where it can be argued with.
#:
#: 2014-2016  thematic short baskets (cannabis, SaaS) plus large-cap longs.
#: 2017-2018  the long micro-cap book appears: SMSI, AEHR, MRIN, HMNY.
#: 2019-2020  a second short basket, then COVID intraday trading — several
#:            positions opened and closed the same day.
#: 2021+      the method the app implements: long micro-caps held months to
#:            years, exited on R/R.
ERA_SHORT_BOOK: Final[str] = "SHORT_BOOK_2014_2016"
ERA_LONG_MICROCAP: Final[str] = "LONG_MICROCAP_2017_2018"
ERA_DAYTRADE: Final[str] = "DAYTRADE_2019_2020"
ERA_MODERN: Final[str] = "MODERN_LONG"

_ERA_BOUNDARIES: Final[tuple[tuple[date, str], ...]] = (
    (date(2017, 1, 1), ERA_SHORT_BOOK),
    (date(2019, 1, 1), ERA_LONG_MICROCAP),
    (date(2021, 1, 1), ERA_DAYTRADE),
)


def era_for(opened: date) -> str:
    """The era an entry opened in. Total: every date lands somewhere."""
    for boundary, era in _ERA_BOUNDARIES:
        if opened < boundary:
            return era
    return ERA_MODERN


# ==============================================================================
# Rows
# ==============================================================================

class DatasetError(Exception):
    """The dataset is not loadable. Never a partial list, never a guess."""


@dataclass(frozen=True)
class Entry:
    """One row of the sheet, with the human labels joined on."""

    row_id: int
    company: str
    ticker: str
    initial_interest: date
    #: None when the sheet left it blank, which means the position is open.
    pause_interest: date | None
    days_claimed: int
    inclination: str
    status: str
    initial_price: float | None
    final_price: float | None
    final_change_pct: float | None
    final_net_change_pct: float | None
    #: Named for what it is. The sheet's "Peak Return While Live" column is
    #: split-contaminated beyond repair — MRIN reads 22394, GSAT 12850, BYND
    #: 5540 — so it is carried as text and never used as a number. `features.py`
    #: recomputes `max_drawup_pct` from adjusted bars instead.
    peak_return_live_pct_unusable: str
    latest_notes: str
    footnote: str

    instrument: str
    exit_kind: str
    #: Empty string for an open position: there is no exit to give a reason for.
    exit_reason: str
    #: `row_id` of the row this one duplicates, or None.
    duplicate_of: int | None
    label_note: str

    @property
    def is_open(self) -> bool:
        return self.pause_interest is None

    @property
    def era(self) -> str:
        return era_for(self.initial_interest)

    @property
    def price_basis(self) -> str:
        """`SPLIT_ADJUSTED` for the two footnoted rows, `AS_QUOTED` otherwise."""
        markers = _markers(self.footnote)
        if markers & SPLIT_ADJUSTED_MARKERS:
            return "SPLIT_ADJUSTED"
        return "AS_QUOTED"

    @property
    def days_actual(self) -> int:
        """Days the sheet's own dates imply. Open rows count to `SHEET_DATE`."""
        end = self.pause_interest or SHEET_DATE
        return (end - self.initial_interest).days


def _markers(footnote: str) -> frozenset[str]:
    """`[6][7]` -> {"[6]", "[7]"}."""
    if not footnote:
        return frozenset()
    parts = [p for p in footnote.replace("[", " [").split() if p.startswith("[")]
    return frozenset(parts)


# ==============================================================================
# Loading
# ==============================================================================

def _rows(path: pathlib.Path) -> Iterator[dict[str, str]]:
    """CSV rows, with `#` comment lines dropped before parsing."""
    if not path.exists():
        raise DatasetError(
            f"Chybí {path.name}. Přepis listu se commituje do "
            f"backend/research/data/ — viz backend/research/README.md."
        )
    with path.open(encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(
            line for line in handle if not line.startswith("#")
        )


def _date(value: str, row_id: str, field: str) -> date | None:
    text = value.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise DatasetError(
            f"Řádek {row_id}: {field} = {text!r} není datum v ISO tvaru."
        ) from exc


def _number(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_entries() -> list[Entry]:
    """
    Every row of the sheet with its labels, or `DatasetError` naming every fault.

    Rows come back in PDF order, which is NOT date order — row 156 sits out of
    sequence in the source and is left there, because `row_id` is the join key
    for every downstream artefact and re-sorting would make it meaningless.
    """
    sheet: dict[int, dict[str, str]] = {}
    faults: list[str] = []

    for raw in _rows(SHEET_CSV):
        key = (raw.get("row_id") or "").strip()
        if not key.isdigit():
            faults.append(f"priority_ideas.csv: row_id = {key!r} není celé číslo")
            continue
        row_id = int(key)
        if row_id in sheet:
            faults.append(f"Řádek {row_id}: row_id je v priority_ideas.csv dvakrát")
            continue
        sheet[row_id] = raw

    labels: dict[int, dict[str, str]] = {}
    for raw in _rows(LABELS_CSV):
        key = (raw.get("row_id") or "").strip()
        if not key.isdigit():
            faults.append(f"priority_ideas_labels.csv: row_id = {key!r} není číslo")
            continue
        row_id = int(key)
        if row_id in labels:
            faults.append(f"Řádek {row_id}: row_id je v labels dvakrát")
            continue
        labels[row_id] = raw

    for row_id in sorted(set(sheet) - set(labels)):
        faults.append(f"Řádek {row_id}: je v přepisu, ale nemá label")
    for row_id in sorted(set(labels) - set(sheet)):
        faults.append(f"Řádek {row_id}: má label, ale v přepisu není")

    entries: list[Entry] = []
    for row_id in sorted(set(sheet) & set(labels)):
        raw, label = sheet[row_id], labels[row_id]
        try:
            entry = _build(row_id, raw, label)
        except DatasetError as exc:
            faults.append(str(exc))
            continue
        faults.extend(_check(entry, raw, label))
        entries.append(entry)

    faults.extend(_check_duplicates(entries))

    if faults:
        raise DatasetError(
            f"Dataset se nedá načíst, {len(faults)} závad:\n  "
            + "\n  ".join(faults)
        )
    return entries


def _build(row_id: int, raw: dict[str, str], label: dict[str, str]) -> Entry:
    key = str(row_id)
    duplicate = (label.get("duplicate_of") or "").strip()
    initial = _date(raw.get("initial_interest", ""), key, "initial_interest")
    if initial is None:
        raise DatasetError(f"Řádek {row_id}: chybí initial_interest")

    days = (raw.get("days") or "").strip()
    if not days.lstrip("-").isdigit():
        raise DatasetError(f"Řádek {row_id}: days = {days!r} není celé číslo")

    return Entry(
        row_id=row_id,
        company=(raw.get("company") or "").strip(),
        ticker=(raw.get("ticker") or "").strip(),
        initial_interest=initial,
        pause_interest=_date(raw.get("pause_interest", ""), key, "pause_interest"),
        days_claimed=int(days),
        inclination=(raw.get("inclination") or "").strip(),
        status=(raw.get("status") or "").strip(),
        initial_price=_number(raw.get("initial_price", "")),
        final_price=_number(raw.get("final_price", "")),
        final_change_pct=_number(raw.get("final_change_pct", "")),
        final_net_change_pct=_number(raw.get("final_net_change_pct", "")),
        peak_return_live_pct_unusable=(raw.get("peak_return_live_pct") or "").strip(),
        latest_notes=(raw.get("latest_notes") or "").strip(),
        footnote=(raw.get("footnote") or "").strip(),
        instrument=(label.get("instrument") or "").strip(),
        exit_kind=(label.get("exit_kind") or "").strip(),
        exit_reason=(label.get("exit_reason") or "").strip(),
        duplicate_of=int(duplicate) if duplicate.isdigit() else None,
        label_note=(label.get("label_note") or "").strip(),
    )


def _check(entry: Entry, raw: dict[str, str], label: dict[str, str]) -> list[str]:
    """Every fault this row has. Empty list means it passed."""
    faults: list[str] = []
    n = entry.row_id

    if entry.ticker != (label.get("ticker") or "").strip():
        faults.append(
            f"Řádek {n}: ticker v přepisu ({entry.ticker!r}) a v labels "
            f"({(label.get('ticker') or '').strip()!r}) se liší"
        )

    if entry.inclination not in INCLINATIONS:
        faults.append(f"Řádek {n}: neznámý inclination {entry.inclination!r}")
    if entry.instrument not in INSTRUMENTS:
        faults.append(f"Řádek {n}: neznámý instrument {entry.instrument!r}")
    if entry.exit_kind not in EXIT_KINDS:
        faults.append(f"Řádek {n}: neznámý exit_kind {entry.exit_kind!r}")

    if entry.is_open:
        # An open position has no exit, so it must not carry a reason for one.
        if entry.exit_reason:
            faults.append(
                f"Řádek {n}: je otevřený, ale nese exit_reason "
                f"{entry.exit_reason!r}"
            )
        if entry.exit_kind != "STILL_OPEN":
            faults.append(
                f"Řádek {n}: prázdný pause_interest, ale exit_kind je "
                f"{entry.exit_kind!r}, ne STILL_OPEN"
            )
        if entry.status:
            faults.append(
                f"Řádek {n}: prázdný pause_interest, ale status je "
                f"{entry.status!r} — list si odporuje, řeší se ručně"
            )
    else:
        if entry.exit_reason not in EXIT_REASONS:
            faults.append(f"Řádek {n}: neznámý exit_reason {entry.exit_reason!r}")
        if entry.exit_kind == "STILL_OPEN":
            faults.append(
                f"Řádek {n}: má pause_interest, ale exit_kind je STILL_OPEN"
            )
        if entry.status != "CLOSED":
            faults.append(
                f"Řádek {n}: má pause_interest, ale status je {entry.status!r}, "
                f"ne CLOSED — list si odporuje, řeší se ručně"
            )
        if entry.pause_interest and entry.pause_interest < entry.initial_interest:
            faults.append(
                f"Řádek {n}: pause_interest {entry.pause_interest} je před "
                f"initial_interest {entry.initial_interest}"
            )

    drift = abs(entry.days_claimed - entry.days_actual)
    if drift > DAYS_TOLERANCE:
        faults.append(
            f"Řádek {n}: list tvrdí {entry.days_claimed} dní, z jeho vlastních "
            f"dat vychází {entry.days_actual} (rozdíl {drift}) — nejspíš "
            f"překlep v roce nebo měsíci"
        )

    for field, value in (
        ("initial_price", entry.initial_price),
        ("final_price", entry.final_price),
    ):
        if value is not None and value < 0:
            faults.append(f"Řádek {n}: {field} = {value} je záporná")
    # An entry price of zero is a fault; an exit price of zero is not — an
    # option that expired worthless really did settle at zero (rows 56, 89, 133).
    if entry.initial_price is not None and entry.initial_price == 0:
        faults.append(f"Řádek {n}: initial_price je nula")

    markers = _markers(entry.footnote)
    unknown = markers - set(FOOTNOTES)
    if unknown:
        faults.append(f"Řádek {n}: neznámá poznámka pod čarou {sorted(unknown)}")
    if entry.price_basis == "SPLIT_ADJUSTED" and not markers:
        faults.append(f"Řádek {n}: price_basis SPLIT_ADJUSTED bez poznámky pod čarou")

    return faults


def _check_duplicates(entries: Iterable[Entry]) -> list[str]:
    """A `duplicate_of` must point at a row that exists and is not itself one."""
    by_id = {entry.row_id: entry for entry in entries}
    faults: list[str] = []
    for entry in by_id.values():
        target = entry.duplicate_of
        if target is None:
            continue
        if target not in by_id:
            faults.append(
                f"Řádek {entry.row_id}: duplicate_of ukazuje na {target}, "
                f"který v datasetu není"
            )
        elif by_id[target].duplicate_of is not None:
            faults.append(
                f"Řádek {entry.row_id}: duplicate_of ukazuje na {target}, "
                f"který je sám označený jako duplikát"
            )
    return faults


# ==============================================================================
# Cohorts
# ==============================================================================

def reference_cohort(entries: Iterable[Entry]) -> list[Entry]:
    """
    The rows the entry profile is built from.

    Long positions in individual stocks, opened under the method the app
    implements, each counted once. Everything the app cannot act on is out:
    shorts (it is long-only), index hedges and options (it has no concept of
    either), and the one row the sheet transcribed twice.

    Deliberately not filtered on outcome. A position opened last week has an
    entry like any other, and dropping it because we cannot yet see how it ended
    would bias the profile towards whatever has had time to work.
    """
    return [
        entry
        for entry in entries
        if entry.instrument == "LONG_EQUITY"
        and entry.era == ERA_MODERN
        and entry.duplicate_of is None
    ]


def decided_exits(entries: Iterable[Entry]) -> list[Entry]:
    """
    Rows whose exit was a decision to sell that name, and nothing else.

    Anything measured about *why* or *when* Mark sells has to run over this and
    not over every closed row. Two kinds of row are excluded, for two different
    reasons:

    * `exit_kind == BATCH` — closed on a day when a pile of unrelated positions
      closed together. On 2016-04-25 eighteen did. Reading eighteen sell
      decisions out of one afternoon's tidying would be reading something that
      is not there.
    * `exit_reason == UKLID` — the sheet had the same position bookmarked twice
      and one bookmark was closed. Nothing was sold: the position continues
      under the other row. 2017-09-19 is four of these in a row, which is why it
      looks like a sweep to `batches.py` and is not one.

    The second exclusion matters as much as the first and is easier to miss,
    because those rows carry a real-looking exit date and a real-looking return.
    """
    return [
        entry
        for entry in entries
        if not entry.is_open
        and entry.exit_kind not in {"BATCH", "STILL_OPEN"}
        and entry.exit_reason != "UKLID"
        and entry.duplicate_of is None
    ]

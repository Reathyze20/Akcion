"""
Which "Pause Interest" dates are housekeeping sweeps rather than decisions.

This is the single most consequential piece of cleaning in the dataset. On
2016-04-25 eighteen unrelated positions close at once; on 2015-06-10 fourteen;
on 2025-01-03 twelve. Reading eighteen sell decisions out of one afternoon's
tidying would produce a confident answer to "when does Mark sell" that measures
nothing.

The machine proposes, the human confirms. This module only proposes: it groups
closed rows by exit date and flags any date carrying `MIN_BATCH_ROWS` or more.
The ruling lives in `exit_kind` in `data/priority_ideas_labels.csv`.

The two are NOT required to agree, and that is the point. Four rows sharing a
date can be a genuine coincidence — 2017-09-19 closes two duplicate MATR
bookmarks, a MRIN and a USAT, each with its own note. What IS required is that
every flagged row was looked at: a row on a candidate date that is labelled
something other than BATCH must carry a `label_note` saying why. Silence is
what the check refuses, not disagreement.

    python -m research.batches
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Final, Iterable

from research.dataset import Entry, load_entries

#: How many positions have to close on one date before it is worth a look.
#:
#: Four, not eight. A higher bar would quietly wave through the tail of the
#: 2016-04-28 short basket, which was unwound in tranches of exactly four
#: (2016-06-24 and 2017-05-12). Set low on purpose: the cost of a false
#: candidate is one sentence in `label_note`, and the cost of a missed sweep is
#: a finding that is not there.
MIN_BATCH_ROWS: Final[int] = 4


@dataclass(frozen=True)
class Candidate:
    """One exit date that closed enough positions to look like a sweep."""

    exit_date: date
    rows: tuple[int, ...]
    tickers: tuple[str, ...]
    #: Rows on this date NOT labelled BATCH — the human's exceptions.
    exceptions: tuple[int, ...]

    @property
    def distinct_tickers(self) -> int:
        return len(set(self.tickers))


def propose(entries: Iterable[Entry]) -> list[Candidate]:
    """Candidate sweep dates, oldest first. Reads labels only to report them."""
    by_date: dict[date, list[Entry]] = defaultdict(list)
    for entry in entries:
        if entry.pause_interest is not None and entry.duplicate_of is None:
            by_date[entry.pause_interest].append(entry)

    candidates: list[Candidate] = []
    for exit_date, rows in sorted(by_date.items()):
        if len(rows) < MIN_BATCH_ROWS:
            continue
        candidates.append(
            Candidate(
                exit_date=exit_date,
                rows=tuple(sorted(row.row_id for row in rows)),
                tickers=tuple(row.ticker for row in rows),
                exceptions=tuple(
                    sorted(
                        row.row_id for row in rows if row.exit_kind != "BATCH"
                    )
                ),
            )
        )
    return candidates


def unexplained(entries: Iterable[Entry]) -> list[str]:
    """
    Candidate rows the human neither marked BATCH nor explained.

    An empty list is what "the cleaning pass is finished" looks like.
    """
    rows = list(entries)
    by_id = {entry.row_id: entry for entry in rows}
    faults: list[str] = []
    for candidate in propose(rows):
        for row_id in candidate.exceptions:
            entry = by_id[row_id]
            if not entry.label_note:
                faults.append(
                    f"Řádek {row_id} ({entry.ticker}): zavřen "
                    f"{candidate.exit_date} spolu s {len(candidate.rows) - 1} "
                    f"dalšími, ale není označen jako BATCH a nemá label_note, "
                    f"který by řekl proč"
                )
    return faults


def main() -> int:
    from research import _bootstrap  # noqa: F401  — cwd, sys.path, console

    entries = load_entries()
    candidates = propose(entries)

    print(f"Kandidáti na hromadnou uzávěrku (>= {MIN_BATCH_ROWS} pozic v jeden den)\n")
    for candidate in candidates:
        marked = len(candidate.rows) - len(candidate.exceptions)
        print(
            f"{candidate.exit_date}  {len(candidate.rows):3d} pozic, "
            f"{candidate.distinct_tickers:3d} různých tickerů  "
            f"-> {marked} označeno BATCH"
        )
        if candidate.exceptions:
            print(f"{'':12}  výjimky: {list(candidate.exceptions)}")

    faults = unexplained(entries)
    print()
    if faults:
        print(f"NEVYSVĚTLENO ({len(faults)}):")
        for fault in faults:
            print(f"  {fault}")
        return 1

    total = sum(len(c.rows) for c in candidates)
    batched = sum(1 for e in entries if e.exit_kind == "BATCH")
    print(
        f"Vše vysvětleno. {len(candidates)} kandidátních dat, {total} řádků na "
        f"nich, {batched} označeno BATCH."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

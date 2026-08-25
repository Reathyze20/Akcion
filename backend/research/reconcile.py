"""
Can the sheet's price for a row be trusted against the tape? One verdict each.

This is the crux of the whole exercise. Every number downstream — the entry
profile, the neighbours, any statistic — is only as good as the answer to "is
this row's $2.41 really where TSSI traded on 10 July 2024, or is it a typo, a
stale quote, or the same company at a different share count?"

The split problem, precisely
---------------------------
Yahoo's data is split-adjusted even in the `Close` column; `Adj Close` is split-
AND dividend-adjusted. Neither is what was quoted on the day. So for any name
that has split since, the sheet and the tape disagree by exactly the cumulative
split ratio, and a naive comparison marks every one of them a mismatch.

The fix is not to accept any factor that looks like a split. That would launder
bad data: a factor of 10 is equally consistent with a 1-for-10 reverse split and
with a decimal point in the wrong place. So `MATCHED_VIA_FACTOR` is granted only
when yfinance itself reports splits in the window, and their product scales that
session's own high/low range onto the sheet's price. The tape has to corroborate
the correction. Without that coupling this module would be a machine for making
wrong prices look right, and it is the failure most likely to quietly poison
everything below it.

The ladder is total: first match wins, and every row gets exactly one verdict
with a machine reason and a Czech one — the same shape as
`score_outcomes.REASON_NO_BASELINE` and friends.

    python -m research.reconcile
    python -m research.reconcile --no-cache
"""

from __future__ import annotations

import argparse
import csv
import pathlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Final, Iterable

from research.dataset import Entry, load_entries
from research.prices import Bars, PriceError, fetch_many

DATA: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parent / "data"
RENAMES_CSV: Final[pathlib.Path] = DATA / "renames.csv"

#: How far the sheet's price may sit outside the session's own high/low range.
#:
#: Half a percent, and the comparison is against the RANGE, not a single close:
#: a price typed during the session should sit somewhere between the low and the
#: high. Tighter than this and ordinary rounding in the sheet fails; looser and
#: a genuinely wrong price on a volatile micro-cap passes.
EPSILON: Final[float] = 0.005

#: There is no hand-written list of plausible split ratios here, and there was
#: one until the data argued it away.
#:
#: The list held integers 2..20 and their reciprocals — which sounds complete
#: until SMSI turns up having reverse-split 1-for-8 and then again, so the
#: cumulative factor is 0.025 and no entry in the list is close. The list was
#: rejecting a correct match.
#:
#: The check it was standing in for is better done by the tape: a factor is
#: accepted only when yfinance itself reports splits in the window whose product
#: scales the session's own high/low range onto the sheet's price. A factor of
#: 10 with no reported split stays a wrong price; a factor of 1.37 can never be
#: corroborated, because exchanges do not report 1.37-for-1 splits. The source
#: is a stricter plausibility filter than a list somebody typed, and it cannot
#: go out of date.

#: Days of history to pull before the first entry and after the last exit.
#: Enough for a 12-month lookback and a 12-month forward return in `features.py`.
LOOKBACK_DAYS: Final[int] = 460
LOOKFORWARD_DAYS: Final[int] = 400

MATCHED_RAW: Final[str] = "MATCHED_RAW"
MATCHED_ADJUSTED: Final[str] = "MATCHED_ADJUSTED"
MATCHED_VIA_FACTOR: Final[str] = "MATCHED_VIA_FACTOR"
MISMATCH_UNEXPLAINED: Final[str] = "MISMATCH_UNEXPLAINED"
NO_DATA_DELISTED: Final[str] = "NO_DATA_DELISTED"
NO_DATA_AT_ALL: Final[str] = "NO_DATA_AT_ALL"
NO_DATA_BEFORE_ENTRY: Final[str] = "NO_DATA_BEFORE_ENTRY"
RENAMED_UNRESOLVED: Final[str] = "RENAMED_UNRESOLVED"
FETCH_FAILED: Final[str] = "FETCH_FAILED"
SKIPPED_NOT_EQUITY: Final[str] = "SKIPPED_NOT_EQUITY"
SKIPPED_DUPLICATE: Final[str] = "SKIPPED_DUPLICATE"
SKIPPED_NO_PRICE: Final[str] = "SKIPPED_NO_PRICE"

MATCHED: Final[frozenset[str]] = frozenset(
    {MATCHED_RAW, MATCHED_ADJUSTED, MATCHED_VIA_FACTOR}
)

REASON_CS: Final[dict[str, str]] = {
    MATCHED_RAW: "Cena z listu sedí na kurz z toho dne.",
    MATCHED_ADJUSTED: (
        "Cena z listu sedí na zpětně přepočtený kurz, ne na kurz z toho dne — "
        "do přepisu se nejspíš dostala dnes zobrazovaná hodnota."
    ),
    MATCHED_VIA_FACTOR: (
        "Cena z listu sedí po zohlednění splitu, který burza sama hlásí."
    ),
    MISMATCH_UNEXPLAINED: (
        "Data existují, ale cena z listu nesedí a žádný hlášený split to "
        "nevysvětlí."
    ),
    NO_DATA_DELISTED: (
        "Kurzy končí dřív, než list pozici zavřel — papír mezitím z burzy zmizel."
    ),
    NO_DATA_AT_ALL: "Pro tenhle symbol nevrací zdroj žádné kurzy.",
    NO_DATA_BEFORE_ENTRY: (
        "Kurzy začínají až po dni vstupu — pod tímhle symbolem se tehdy "
        "neobchodovalo."
    ),
    RENAMED_UNRESOLVED: (
        "Symbol je mrtvý a nástupce není v renames.csv — nikdo ho zatím nedohledal."
    ),
    FETCH_FAILED: "Stažení historie selhalo. Není to fakt o firmě, je to o síti.",
    SKIPPED_NOT_EQUITY: "Není to dlouhá pozice v akcii — profil se z toho nestaví.",
    SKIPPED_DUPLICATE: "Řádek je v listu podruhé; počítá se ten první.",
    SKIPPED_NO_PRICE: "List u tohohle řádku vstupní cenu neuvádí.",
}


# ==============================================================================
# Renames
# ==============================================================================

@dataclass(frozen=True)
class Rename:
    """
    One dead symbol, and what became of it.

    Deliberately NOT in `app/core/tickers.py`. That table is about simultaneous
    dual listings — `canonical_ticker` is a symmetric, time-independent
    equivalence, and `KUYA.V` and `KUYAF` are the same company today. A rename
    is neither symmetric nor timeless: USAT became CTLP on a date, and a 2015
    USAT row is not a 2026 CTLP position. Putting it there would make
    `same_company("USAT", "CTLP")` true today, merge two unrelated rows in the
    ladder view, and send a dead symbol to Yahoo on every refresh.
    """

    old_ticker: str
    #: Empty when there is no successor series. That is a positive statement —
    #: the company is gone — and different from "nobody looked", which is the
    #: symbol being absent from the file entirely.
    new_ticker: str
    effective_date: date | None
    kind: str
    evidence: str


def load_renames() -> dict[str, Rename]:
    if not RENAMES_CSV.exists():
        return {}
    renames: dict[str, Rename] = {}
    with RENAMES_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(
            line for line in handle if not line.startswith("#")
        ):
            when = (row.get("effective_date") or "").strip()
            renames[row["old_ticker"].strip().upper()] = Rename(
                old_ticker=row["old_ticker"].strip().upper(),
                new_ticker=(row.get("new_ticker") or "").strip().upper(),
                effective_date=date.fromisoformat(when) if when else None,
                kind=(row.get("kind") or "").strip(),
                evidence=(row.get("evidence") or "").strip(),
            )
    return renames


# ==============================================================================
# One row's verdict
# ==============================================================================

@dataclass(frozen=True)
class Verdict:
    """What can be said about one row's entry price."""

    row_id: int
    ticker: str
    #: The symbol actually queried, after any rename.
    resolved_ticker: str
    verdict: str
    sheet_price: float | None
    #: The session the comparison ran against.
    bar_date: date | None = None
    raw_close: float | None = None
    adj_close: float | None = None
    #: sheet_price / raw_close, when a factor was needed to explain the gap.
    factor: float | None = None
    #: The product of split events the tape reports in the window.
    split_product: float | None = None
    note: str = ""

    @property
    def matched(self) -> bool:
        return self.verdict in MATCHED

    @property
    def reason_cs(self) -> str:
        return REASON_CS.get(self.verdict, "")


def _within(price: float, low: float, high: float) -> bool:
    return low * (1 - EPSILON) <= price <= high * (1 + EPSILON)


def reconcile_entry(entry: Entry, bars: Bars | PriceError | None) -> Verdict:
    """
    One row against its bars. Total — every input produces exactly one verdict.

    Candidate sessions are the entry day and the one before it: Mark writes
    ideas up in the evening, so the price he noted may be the prior close.
    """
    resolved = entry.ticker

    if entry.duplicate_of is not None:
        return Verdict(entry.row_id, entry.ticker, resolved, SKIPPED_DUPLICATE,
                       entry.initial_price)
    if entry.instrument != "LONG_EQUITY":
        return Verdict(entry.row_id, entry.ticker, resolved, SKIPPED_NOT_EQUITY,
                       entry.initial_price)
    if entry.initial_price is None:
        return Verdict(entry.row_id, entry.ticker, resolved, SKIPPED_NO_PRICE, None)

    if isinstance(bars, PriceError):
        return Verdict(entry.row_id, entry.ticker, resolved, FETCH_FAILED,
                       entry.initial_price, note=str(bars))
    if bars is None:
        return Verdict(entry.row_id, entry.ticker, resolved, NO_DATA_AT_ALL,
                       entry.initial_price)

    resolved = bars.ticker

    if bars.is_empty:
        return Verdict(entry.row_id, entry.ticker, resolved, NO_DATA_AT_ALL,
                       entry.initial_price)

    # Bars that stop before the position closed mean the symbol died mid-life.
    # A week of slack: the last session and the sheet's date rarely coincide.
    end = entry.pause_interest
    if end is not None and bars.last_day and bars.last_day < end - timedelta(days=7):
        return Verdict(
            entry.row_id, entry.ticker, resolved, NO_DATA_DELISTED,
            entry.initial_price, bar_date=bars.last_day,
        )

    bar = bars.on_or_after(entry.initial_interest)
    if bar is None:
        return Verdict(entry.row_id, entry.ticker, resolved, NO_DATA_DELISTED,
                       entry.initial_price, bar_date=bars.last_day)

    previous = bars.on_or_before(entry.initial_interest - timedelta(days=1))
    if previous is None and bars.first_day and bars.first_day > entry.initial_interest:
        return Verdict(entry.row_id, entry.ticker, resolved, NO_DATA_BEFORE_ENTRY,
                       entry.initial_price, bar_date=bars.first_day)

    price = entry.initial_price
    candidates = [b for b in (bar, previous) if b is not None]

    for candidate in candidates:
        if _within(price, candidate.low, candidate.high):
            return Verdict(
                entry.row_id, entry.ticker, resolved, MATCHED_RAW, price,
                bar_date=candidate.day, raw_close=candidate.close,
                adj_close=candidate.adj_close,
            )

    # The adjusted series differs from the raw one only by dividends, so a match
    # here and not above means the transcription used a currently-displayed
    # figure rather than the historical one. A finding, not a clean pass.
    for candidate in candidates:
        span = candidate.adj_close / candidate.close if candidate.close else 1.0
        if _within(price, candidate.low * span, candidate.high * span):
            return Verdict(
                entry.row_id, entry.ticker, resolved, MATCHED_ADJUSTED, price,
                bar_date=candidate.day, raw_close=candidate.close,
                adj_close=candidate.adj_close,
                note="cena odpovídá zpětně přepočtené řadě, ne kurzu z toho dne",
            )

    # A split between the entry and the end of the series scales the whole tape
    # away from what was quoted. The correction is only accepted when the tape
    # itself reports the split that would produce exactly this factor.
    split_product = bars.cumulative_split(entry.initial_interest, bars.last_day)
    factor = price / bar.close if bar.close else 0.0
    if (
        split_product not in (0.0, 1.0)
        and _within(price, bar.low * split_product, bar.high * split_product)
    ):
        return Verdict(
            entry.row_id, entry.ticker, resolved, MATCHED_VIA_FACTOR, price,
            bar_date=bar.day, raw_close=bar.close, adj_close=bar.adj_close,
            factor=factor, split_product=split_product,
        )

    return Verdict(
        entry.row_id, entry.ticker, resolved, MISMATCH_UNEXPLAINED, price,
        bar_date=bar.day, raw_close=bar.close, adj_close=bar.adj_close,
        factor=factor if bar.close else None,
        split_product=split_product,
        note=(
            f"faktor {factor:.4f}, split podle burzy {split_product:.4f}"
            if bar.close else "kurz z toho dne je nula"
        ),
    )


# ==============================================================================
# The run
# ==============================================================================

@dataclass
class Coverage:
    """Verdict counts, split by era, so bias is visible rather than inferred."""

    by_verdict: Counter = field(default_factory=Counter)
    by_era: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))

    def add(self, entry: Entry, verdict: Verdict) -> None:
        self.by_verdict[verdict.verdict] += 1
        self.by_era[entry.era][verdict.verdict] += 1

    def matched_in(self, era: str) -> int:
        return sum(self.by_era[era][v] for v in MATCHED)

    def considered_in(self, era: str) -> int:
        """Rows the ladder actually judged — skipped rows are not failures."""
        counts = self.by_era[era]
        skipped = (
            counts[SKIPPED_NOT_EQUITY] + counts[SKIPPED_DUPLICATE]
            + counts[SKIPPED_NO_PRICE]
        )
        return sum(counts.values()) - skipped


def reconcile_all(
    entries: Iterable[Entry], bars: dict[str, Bars | PriceError]
) -> list[Verdict]:
    """
    A verdict per row, with dead symbols sent to their successor first.

    The successor lookup runs ONE WAY. A query for CTLP finds the rows the sheet
    filed under USAT; a query for USAT never claims to be CTLP. Two-way would
    make a 2015 USAT row and a 2026 CTLP position the same thing, which is the
    exact error that keeps this table out of `app/core/tickers.py`.

    An empty series with no entry in `renames.csv` is `RENAMED_UNRESOLVED` — the
    remaining hand-work, not a result. An empty series WITH an entry that names
    no successor is `NO_DATA_DELISTED`: somebody looked, and the answer is that
    the series is gone. Keeping those two apart is what makes the queue finite.
    """
    renames = load_renames()
    verdicts: list[Verdict] = []

    for entry in entries:
        if (
            entry.duplicate_of is not None
            or entry.instrument != "LONG_EQUITY"
            or entry.initial_price is None
        ):
            verdicts.append(reconcile_entry(entry, bars.get(entry.ticker)))
            continue

        found = bars.get(entry.ticker)
        if found is None or (isinstance(found, Bars) and found.is_empty):
            rename = renames.get(entry.ticker.upper())
            if rename is None:
                verdicts.append(
                    Verdict(entry.row_id, entry.ticker, entry.ticker,
                            RENAMED_UNRESOLVED, entry.initial_price)
                )
                continue

            successor = bars.get(rename.new_ticker) if rename.new_ticker else None
            if isinstance(successor, Bars) and not successor.is_empty:
                verdicts.append(reconcile_entry(entry, successor))
                continue

            verdicts.append(
                Verdict(
                    entry.row_id, entry.ticker, rename.new_ticker or entry.ticker,
                    NO_DATA_DELISTED, entry.initial_price,
                    note=f"{rename.kind}: {rename.evidence}",
                )
            )
            continue

        verdicts.append(reconcile_entry(entry, found))
    return verdicts


def tickers_to_fetch(entries: Iterable[Entry]) -> set[str]:
    """Every symbol the ladder might need, successors included."""
    renames = load_renames()
    wanted: set[str] = set()
    for entry in entries:
        if entry.instrument != "LONG_EQUITY" or entry.duplicate_of is not None:
            continue
        wanted.add(entry.ticker)
        rename = renames.get(entry.ticker.upper())
        if rename and rename.new_ticker:
            wanted.add(rename.new_ticker)
    return wanted


def main() -> int:
    from research import _bootstrap  # noqa: F401
    from research._bootstrap import out_dir

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-cache", action="store_true",
                        help="ignore out/bars/ and refetch everything")
    parser.add_argument("--era", default=None, help="fetch only one era's tickers")
    args = parser.parse_args()

    entries = load_entries()
    if args.era:
        entries = [e for e in entries if e.era == args.era]

    wanted = tickers_to_fetch(entries)
    dated = [e for e in entries if e.instrument == "LONG_EQUITY"]
    start = min(e.initial_interest for e in dated) - timedelta(days=LOOKBACK_DAYS)
    end = max(
        (e.pause_interest or date.today()) for e in dated
    ) + timedelta(days=LOOKFORWARD_DAYS)

    print(f"Stahuju {len(wanted)} symbolů, {start} .. {end}")

    def progress(index: int, ticker: str, result) -> None:
        if isinstance(result, PriceError):
            state = "CHYBA"
        elif result.is_empty:
            state = "prázdno"
        else:
            state = f"{len(result)} seancí {result.first_day}..{result.last_day}"
        print(f"  [{index:3d}/{len(wanted)}] {ticker:10s} {state}")

    bars = fetch_many(
        wanted, start, end, use_cache=not args.no_cache, on_progress=progress
    )
    verdicts = reconcile_all(entries, bars)

    coverage = Coverage()
    by_id = {e.row_id: e for e in entries}
    for verdict in verdicts:
        coverage.add(by_id[verdict.row_id], verdict)

    out = out_dir()
    with (out / "reconciliation.csv").open("w", encoding="utf-8", newline="") as h:
        writer = csv.writer(h)
        writer.writerow([
            "row_id", "ticker", "resolved_ticker", "verdict", "sheet_price",
            "bar_date", "raw_close", "adj_close", "factor", "split_product",
            "note", "reason_cs",
        ])
        for v in verdicts:
            writer.writerow([
                v.row_id, v.ticker, v.resolved_ticker, v.verdict, v.sheet_price,
                v.bar_date or "", v.raw_close or "", v.adj_close or "",
                v.factor or "", v.split_product or "", v.note, v.reason_cs,
            ])

    lines = ["Smíření cen — souhrn", ""]
    for verdict, count in coverage.by_verdict.most_common():
        lines.append(f"  {verdict:24s} {count:4d}")
    lines.append("")
    lines.append("Pokrytí podle éry (jen posuzované řádky):")
    for era in sorted(coverage.by_era):
        considered = coverage.considered_in(era)
        matched = coverage.matched_in(era)
        share = f"{matched / considered * 100:.0f} %" if considered else "—"
        lines.append(f"  {era:24s} {matched:3d}/{considered:3d}  {share}")

    from research.dataset import ERA_MODERN
    modern = coverage.matched_in(ERA_MODERN)
    lines += [
        "",
        f"Smířených řádků moderní éry: {modern}",
        (
            "Pod 30 se referenční profil nepublikuje; pod 40 se publikuje bez "
            "nejpodobnějších vstupů."
        ),
        "",
        (
            "Pozor na vychýlení: pokud moderní éra sedí výrazně líp než starší, "
            "je každý závěr níž závěrem o moderní éře, ne o metodě obecně."
        ),
    ]
    report = "\n".join(lines)
    (out / "reconciliation_summary.txt").write_text(report + "\n", encoding="utf-8")
    print("\n" + report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

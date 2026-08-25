"""
Feature vectors for every entry the price reconciliation could vouch for.

Thin on purpose. The arithmetic lives in `app/services/entry_features.py` so
that a candidate scored today and the reference distribution it is scored
against go through one and the same function; this module only decides WHICH
rows get one, joins the market context on, and writes the result out.

Two rules it enforces and the maths cannot:

* Only rows the reconciliation matched. A feature vector built on a price the
  tape does not recognise is a confident number about a company that never
  traded there.
* The seventh feature, `gauge_z_at_entry`, is joined here rather than computed
  in `entry_features`, because it is a fact about the market and not about the
  company — a different series, a different failure mode (`GaugeError` when
  there is not thirty years of history yet), and it must stay separable.

    python -m research.features
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final, Iterable

from app.services.entry_features import (
    Bars,
    EntryFeatures,
    FeatureError,
    Outcome,
    compute,
    outcome,
)
from app.services.market_gauge import GaugeError, fit
from research.dataset import Entry, load_entries
from research.prices import PriceError, fetch_many
from research.reconcile import (
    LOOKBACK_DAYS,
    LOOKFORWARD_DAYS,
    MATCHED,
    load_renames,
    reconcile_all,
    tickers_to_fetch,
)

#: The market-context feature, joined on here.
GAUGE_FEATURE: Final[str] = "gauge_z_at_entry"


@dataclass(frozen=True)
class EntryRow:
    """One reconciled entry: what it looked like, and what happened after."""

    entry: Entry
    features: EntryFeatures
    #: None when the gauge refuses — before roughly 2015 there is not thirty
    #: years of index history, and `MIN_YEARS` is not softened to reach further.
    gauge_z: float | None
    gauge_percentile: float | None
    result: Outcome | None
    #: Names of every feature that could not be computed, gauge included.
    missing: tuple[str, ...]

    @property
    def row_id(self) -> int:
        return self.entry.row_id

    @property
    def ticker(self) -> str:
        return self.entry.ticker

    def get(self, name: str) -> float | None:
        if name == GAUGE_FEATURE:
            return self.gauge_z
        return self.features.get(name)


def build(
    entries: Iterable[Entry],
    bars: dict[str, Bars | PriceError],
    index_points: list[tuple[date, float]] | None,
) -> list[EntryRow]:
    """
    A feature vector per reconciled entry, in sheet order.

    Rows the reconciliation could not vouch for are absent rather than present
    with gaps: the whole point of `reconcile.py` is that a price the tape does
    not recognise never becomes a data point.
    """
    renames = load_renames()
    verdicts = {v.row_id: v for v in reconcile_all(entries, bars)}
    rows: list[EntryRow] = []

    for entry in entries:
        verdict = verdicts.get(entry.row_id)
        if verdict is None or verdict.verdict not in MATCHED:
            continue

        found = bars.get(entry.ticker)
        if not isinstance(found, Bars) or found.is_empty:
            rename = renames.get(entry.ticker.upper())
            successor = (
                bars.get(rename.new_ticker) if rename and rename.new_ticker else None
            )
            if not isinstance(successor, Bars) or successor.is_empty:
                continue
            found = successor

        try:
            features = compute(found, entry.initial_interest)
        except FeatureError:
            continue

        gauge_z = gauge_pct = None
        if index_points:
            try:
                reading = fit(index_points, as_of=entry.initial_interest)
                gauge_z, gauge_pct = reading.z_score, reading.percentile
            except GaugeError:
                gauge_z = gauge_pct = None

        missing = list(features.missing)
        if gauge_z is None:
            missing.append(GAUGE_FEATURE)

        rows.append(
            EntryRow(
                entry=entry,
                features=features,
                gauge_z=gauge_z,
                gauge_percentile=gauge_pct,
                result=outcome(found, entry.initial_interest, entry.pause_interest),
                missing=tuple(missing),
            )
        )
    return rows


_COLUMNS: Final[tuple[str, ...]] = (
    "row_id", "ticker", "company", "era", "instrument", "exit_kind",
    "exit_reason", "initial_interest", "pause_interest", "bar_date", "close",
    "drawdown_from_52w_high_pct", "pct_of_52w_range", "ret_6m_pct",
    "vol_60d_annualised_pct", "median_dollar_volume_20d", "price_level",
    "gauge_z_at_entry", "gauge_percentile_at_entry",
    "ret_1m_pct", "ret_3m_pct", "ret_12m_pct", "dist_from_200d_ma_pct",
    "ret_to_exit_pct", "max_drawup_pct", "max_drawdown_pct", "sessions_live",
    "sheet_final_net_change_pct", "missing",
)


def write_csv(rows: Iterable[EntryRow], path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(_COLUMNS)
        for row in rows:
            f, e, o = row.features, row.entry, row.result
            writer.writerow([
                e.row_id, e.ticker, e.company, e.era, e.instrument, e.exit_kind,
                e.exit_reason, e.initial_interest, e.pause_interest or "",
                f.bar_date, f"{f.close:.6f}",
                _fmt(f.drawdown_from_52w_high_pct), _fmt(f.pct_of_52w_range),
                _fmt(f.ret_6m_pct), _fmt(f.vol_60d_annualised_pct),
                _fmt(f.median_dollar_volume_20d, 2), _fmt(f.price_level),
                _fmt(row.gauge_z, 4), _fmt(row.gauge_percentile),
                _fmt(f.ret_1m_pct), _fmt(f.ret_3m_pct), _fmt(f.ret_12m_pct),
                _fmt(f.dist_from_200d_ma_pct),
                _fmt(o.ret_to_exit_pct) if o else "",
                _fmt(o.max_drawup_pct) if o else "",
                _fmt(o.max_drawdown_pct) if o else "",
                o.sessions if o else "",
                # The sheet's own number, kept alongside as a cross-check: a gap
                # of more than a few points after reconciliation means the
                # reconciliation is wrong, not the sheet.
                _fmt(e.final_net_change_pct),
                " ".join(row.missing),
            ])


def _fmt(value: float | None, places: int = 4) -> str:
    return "" if value is None else f"{value:.{places}f}"


def main() -> int:
    from research import _bootstrap  # noqa: F401
    from research._bootstrap import out_dir
    from app.services.market_gauge import fetch_series

    entries = load_entries()
    wanted = tickers_to_fetch(entries)
    dated = [e for e in entries if e.instrument == "LONG_EQUITY"]
    start = min(e.initial_interest for e in dated) - timedelta(days=LOOKBACK_DAYS)
    end = max(
        (e.pause_interest or date.today()) for e in dated
    ) + timedelta(days=LOOKFORWARD_DAYS)

    print(f"Kurzy: {len(wanted)} symbolů (z cache, pokud je čerstvá)")
    bars = fetch_many(wanted, start, end)

    try:
        index_points = fetch_series()
        print(f"Index: {len(index_points)} měsíců ^GSPC")
    except GaugeError as exc:
        # A named absence, not a silent zero: without the index the seventh
        # feature is missing on every row and the report has to say so.
        index_points = None
        print(f"Index se nepodařilo stáhnout ({exc}) — semafor bude chybět všude")

    rows = build(entries, bars, index_points)
    out = out_dir()
    write_csv(rows, out / "features.csv")

    from research.dataset import ERA_MODERN
    modern = [r for r in rows if r.entry.era == ERA_MODERN]
    print(f"\nSpočítáno {len(rows)} vektorů, z toho {len(modern)} v moderní éře.")

    gaps: dict[str, int] = {}
    for row in modern:
        for name in row.missing:
            gaps[name] = gaps.get(name, 0) + 1
    if gaps:
        print("Chybějící vlastnosti v moderní éře (pojmenovaně, ne dopočítané):")
        for name, count in sorted(gaps.items(), key=lambda kv: -kv[1]):
            print(f"  {name:32s} {count:3d}×")
    else:
        print("V moderní éře nechybí žádná vlastnost.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

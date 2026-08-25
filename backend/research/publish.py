"""
Hand the app the two flat files it reads, and nothing else.

`backend/app/data/` holds derived artefacts that are COMMITTED. That is unusual
enough to justify: the app must not depend on anybody having run a research
script, and its inputs should be reviewable in a diff. Research owns the
transformation; the app reads a table with no judgement left in it and never
imports anything from `research/`.

Two files:

* `gomes_entry_profile.json` — the reference distribution for
  `app/services/gomes_fit.py`
* `gomes_registry.csv` — one row per entry Mark ever opened, for the per-company
  history line on the decision board

The registry covers the WHOLE sheet, not just the reconciled modern cohort. "How
many times has Mark been in this name since 2015" is answerable from the
transcription alone, and it stays answerable for companies whose price history
Yahoo has dropped.

    python -m research.publish
"""

from __future__ import annotations

import csv
import json
import pathlib
from datetime import date
from typing import Final, Iterable

from research.dataset import SHEET_CSV, Entry
from research.features import EntryRow
from research.profile import Profile

APP_DATA: Final[pathlib.Path] = (
    pathlib.Path(__file__).resolve().parent.parent / "app" / "data"
)
PROFILE_JSON: Final[pathlib.Path] = APP_DATA / "gomes_entry_profile.json"
REGISTRY_CSV: Final[pathlib.Path] = APP_DATA / "gomes_registry.csv"

_REGISTRY_COLUMNS: Final[tuple[str, ...]] = (
    "row_id", "ticker", "company", "entry_date", "exit_date", "era",
    "instrument", "exit_kind", "exit_reason", "sheet_return_pct", "reconciled",
    "note",
)


def write_profile(profile: Profile, path: pathlib.Path = PROFILE_JSON) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": profile.generated_at,
        "source": profile.source,
        "cohort": profile.cohort,
        "features": {
            name: quantiles.as_dict()
            for name, quantiles in profile.features.items()
        },
        "entries": [
            {
                "row_id": entry.row_id,
                "ticker": entry.ticker,
                "entry_date": entry.entry_date,
                "exit_date": entry.exit_date,
                "exit_kind": entry.exit_kind,
                "exit_reason": entry.exit_reason,
                "note": entry.note,
                "sheet_return_pct": entry.sheet_return_pct,
                "features": {
                    name: round(value, 6)
                    for name, value in sorted(entry.features.items())
                },
            }
            for entry in profile.entries
        ],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_registry(
    entries: Iterable[Entry],
    reconciled: set[int],
    path: pathlib.Path = REGISTRY_CSV,
) -> None:
    """
    Every entry in the sheet, duplicates excluded, with a flag for verified.

    `reconciled` marks the rows whose entry price the tape confirmed. The board
    line uses it to say how much of a company's history is checked, rather than
    presenting a transcription and a verified price as the same thing.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(_REGISTRY_COLUMNS)
        for entry in sorted(
            (e for e in entries if e.duplicate_of is None),
            key=lambda e: (e.ticker, e.initial_interest),
        ):
            writer.writerow([
                entry.row_id, entry.ticker, entry.company,
                entry.initial_interest.isoformat(),
                entry.pause_interest.isoformat() if entry.pause_interest else "",
                entry.era, entry.instrument, entry.exit_kind, entry.exit_reason,
                "" if entry.final_net_change_pct is None
                else f"{entry.final_net_change_pct:.1f}",
                "1" if entry.row_id in reconciled else "0",
                entry.latest_notes,
            ])


def main() -> int:
    from research import _bootstrap  # noqa: F401
    from research._bootstrap import out_dir
    from app.services.market_gauge import GaugeError, fetch_series
    from research.dataset import load_entries
    from research.features import build as build_features
    from research.prices import fetch_many
    from research.profile import ProfileError, build as build_profile
    from research.reconcile import (
        LOOKBACK_DAYS, LOOKFORWARD_DAYS, MATCHED, reconcile_all, tickers_to_fetch,
    )
    from datetime import timedelta

    entries = load_entries()
    wanted = tickers_to_fetch(entries)
    dated = [e for e in entries if e.instrument == "LONG_EQUITY"]
    start = min(e.initial_interest for e in dated) - timedelta(days=LOOKBACK_DAYS)
    end = max(
        (e.pause_interest or date.today()) for e in dated
    ) + timedelta(days=LOOKFORWARD_DAYS)

    print(f"Kurzy: {len(wanted)} symbolů")
    bars = fetch_many(wanted, start, end)

    verdicts = reconcile_all(entries, bars)
    reconciled = {v.row_id for v in verdicts if v.verdict in MATCHED}
    excluded: dict[str, int] = {}
    for verdict in verdicts:
        if verdict.verdict not in MATCHED and not verdict.verdict.startswith("SKIPPED"):
            excluded[verdict.verdict] = excluded.get(verdict.verdict, 0) + 1

    try:
        index_points = fetch_series()
    except GaugeError as exc:
        print(f"Index se nepodařilo stáhnout ({exc}) — semafor bude chybět")
        index_points = None

    rows = build_features(entries, bars, index_points)

    sheet_stamp = SHEET_CSV.stat().st_mtime
    source = (
        f"priority_ideas.csv ({len(entries)} řádků, PDF z 24. 8. 2026), "
        f"mtime {date.fromtimestamp(sheet_stamp)}"
    )

    try:
        profile = build_profile(
            rows,
            generated_at=date.today().isoformat(),
            source=source,
            excluded=excluded,
        )
    except ProfileError as exc:
        print(f"\n{exc}")
        print("Rejstřík se publikuje i tak — na smíření cen nezávisí.")
        write_registry(entries, reconciled)
        print(f"Zapsáno: {REGISTRY_CSV.relative_to(APP_DATA.parent.parent)}")
        return 1

    write_profile(profile)
    write_registry(entries, reconciled)

    print(f"\nProfil: {profile.n_rows} vstupů, {profile.n_tickers} tickerů, "
          f"{profile.cohort['first_entry']} .. {profile.cohort['last_entry']}")
    print(f"  sousedi: {'ano' if profile.supports_neighbours else 'NE (málo dat)'}")
    print(f"  vyloučeno: {excluded or 'nic'}")
    for name, quantiles in profile.features.items():
        print(
            f"  {name:28s} n={quantiles.n:3d}  "
            f"p25 {quantiles.p25:9.2f}  medián {quantiles.median:9.2f}  "
            f"p75 {quantiles.p75:9.2f}"
        )
    print(f"\nZapsáno:\n  {PROFILE_JSON}\n  {REGISTRY_CSV}")
    (out_dir() / "publish.txt").write_text(
        f"{profile.n_rows} vstupů, {profile.n_tickers} tickerů\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

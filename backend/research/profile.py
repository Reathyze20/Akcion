"""
The reference distribution: what a Mark Gomes entry looks like.

Turns the reconciled feature vectors into the file `app/services/gomes_fit.py`
reads — per feature a handful of quantiles, plus the entries themselves so a
candidate can be told which of them it most resembles.

Three things this file is careful about.

**It carries its own composition.** Row counts, distinct tickers, and what was
excluded and why, all inside the published artefact. Without that it reads like
"Mark's rules" when it is a sample of forty, and the difference is the whole
distance between a fact and a claim.

**It counts tickers as well as rows.** Fifty entries across thirty names is not
fifty independent observations — VTSI alone is five of them. Nothing here fits
anything, so that does not invalidate a quantile, but any reader deciding how
much to trust the spread needs the second number.

**Quantiles, not a fitted shape.** No normal, no kernel. Forty points support
"here is where the middle half sat" and do not support a density.

    python -m research.profile
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Final, Iterable, Sequence

from app.services.entry_features import PROFILE_FEATURES
from research.dataset import ERA_MODERN
from research.features import GAUGE_FEATURE, EntryRow

#: Every feature the profile describes: the six chart ones plus the market one.
PROFILE_ALL: Final[tuple[str, ...]] = PROFILE_FEATURES + (GAUGE_FEATURE,)

#: Below this many reconciled entries the profile is not published at all.
#:
#: Thirty is not a magic number; it is the point below which the quantiles stop
#: describing anything. p10 of twenty-five points is the third-smallest value,
#: and calling that "the bottom tenth" overstates it enough to mislead.
MIN_ENTRIES: Final[int] = 30

#: Below this, the profile publishes but the nearest-neighbour list does not.
#:
#: Neighbours are the most persuasive thing on the screen and the least robust:
#: three closest points out of thirty-five is an anecdote wearing a distance
#: metric. Forty is still few, which is why the tool prints them with the
#: distances and a line saying they are cases, not evidence.
MIN_FOR_NEIGHBOURS: Final[int] = 40


class ProfileError(Exception):
    """Not enough reconciled entries to describe anything."""


@dataclass(frozen=True)
class Quantiles:
    """Where one feature's values sat across the cohort."""

    n: int
    minimum: float
    p10: float
    p25: float
    median: float
    p75: float
    p90: float
    maximum: float

    def bucket(self, value: float) -> str:
        """
        Where a candidate's value falls: TYPICKE, NA_OKRAJI or MIMO.

        Coarse on purpose. A percentile printed off forty points ("82. percentil")
        claims a precision the sample does not have; three buckets plus the raw
        count of how many entries sat lower is what forty points can honestly say.
        """
        if self.p25 <= value <= self.p75:
            return "TYPICKE"
        if self.p10 <= value <= self.p90:
            return "NA_OKRAJI"
        return "MIMO"

    def as_dict(self) -> dict[str, float | int]:
        return {
            "n": self.n, "min": self.minimum, "p10": self.p10, "p25": self.p25,
            "median": self.median, "p75": self.p75, "p90": self.p90,
            "max": self.maximum,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Quantiles":
        return cls(
            n=int(raw["n"]), minimum=float(raw["min"]), p10=float(raw["p10"]),
            p25=float(raw["p25"]), median=float(raw["median"]),
            p75=float(raw["p75"]), p90=float(raw["p90"]),
            maximum=float(raw["max"]),
        )


def quantiles_of(values: Sequence[float]) -> Quantiles | None:
    """Quantiles for one feature, or None when there are too few values."""
    data = sorted(values)
    if len(data) < 4:  # `statistics.quantiles` needs at least two, this needs shape
        return None
    cuts = statistics.quantiles(data, n=100, method="inclusive")
    return Quantiles(
        n=len(data),
        minimum=data[0],
        p10=cuts[9],
        p25=cuts[24],
        median=statistics.median(data),
        p75=cuts[74],
        p90=cuts[89],
        maximum=data[-1],
    )


@dataclass(frozen=True)
class ProfileEntry:
    """One of Mark's entries, kept so a candidate can be told what it resembles."""

    row_id: int
    ticker: str
    entry_date: str
    exit_date: str
    exit_kind: str
    exit_reason: str
    note: str
    #: The sheet's own return. NOT the one recomputed from bars: his exits are
    #: intraday decision prices that beat the close in 25 of 31 modern cases, so
    #: the bars answer a different question. See
    #: `tests/test_research_features.py::test_the_sheet_exits_above_the_close...`
    sheet_return_pct: float | None
    features: dict[str, float]


@dataclass(frozen=True)
class Profile:
    """The published reference distribution, with its own composition attached."""

    generated_at: str
    source: str
    cohort: dict
    features: dict[str, Quantiles]
    entries: tuple[ProfileEntry, ...]

    @property
    def n_rows(self) -> int:
        return int(self.cohort.get("n_rows", 0))

    @property
    def n_tickers(self) -> int:
        return int(self.cohort.get("n_tickers", 0))

    @property
    def supports_neighbours(self) -> bool:
        return self.n_rows >= MIN_FOR_NEIGHBOURS

    def share_at_or_above(self, feature: str, threshold: float) -> tuple[int, int]:
        """
        How many entries sat at or above a threshold, and out of how many.

        For `gauge_z_at_entry`, which is a fact about the market rather than
        about the company. A quantile bucket there would invite reading a
        precision into a seven-point spread that is not in it; "twelve of forty"
        is what the data says.
        """
        values = [
            e.features[feature] for e in self.entries if feature in e.features
        ]
        return sum(1 for v in values if v >= threshold), len(values)


def build(
    rows: Iterable[EntryRow],
    *,
    generated_at: str,
    source: str,
    excluded: dict[str, int] | None = None,
) -> Profile:
    """
    The distribution over the modern-era long-equity entries that reconciled.

    Raises `ProfileError` below `MIN_ENTRIES` rather than publishing quantiles
    that describe nothing.
    """
    cohort = [row for row in rows if row.entry.era == ERA_MODERN]
    if len(cohort) < MIN_ENTRIES:
        raise ProfileError(
            f"Smířených vstupů moderní éry je jen {len(cohort)}, na rozdělení "
            f"je potřeba aspoň {MIN_ENTRIES}. Profil nevydávám."
        )

    features: dict[str, Quantiles] = {}
    for name in PROFILE_ALL:
        values = [
            row.get(name) for row in cohort if row.get(name) is not None
        ]
        computed = quantiles_of([v for v in values if v is not None])
        if computed is not None:
            features[name] = computed

    entries = tuple(
        ProfileEntry(
            row_id=row.entry.row_id,
            ticker=row.entry.ticker,
            entry_date=row.entry.initial_interest.isoformat(),
            exit_date=(
                row.entry.pause_interest.isoformat()
                if row.entry.pause_interest else ""
            ),
            exit_kind=row.entry.exit_kind,
            exit_reason=row.entry.exit_reason,
            note=row.entry.latest_notes,
            sheet_return_pct=row.entry.final_net_change_pct,
            features={
                name: value
                for name in PROFILE_ALL
                if (value := row.get(name)) is not None
            },
        )
        for row in cohort
    )

    return Profile(
        generated_at=generated_at,
        source=source,
        cohort={
            "era": ERA_MODERN,
            "instrument": "LONG_EQUITY",
            "n_rows": len(cohort),
            "n_tickers": len({row.entry.ticker for row in cohort}),
            "n_open": sum(1 for row in cohort if row.entry.is_open),
            "first_entry": min(r.entry.initial_interest for r in cohort).isoformat(),
            "last_entry": max(r.entry.initial_interest for r in cohort).isoformat(),
            "excluded": excluded or {},
            "supports_neighbours": len(cohort) >= MIN_FOR_NEIGHBOURS,
        },
        features=features,
        entries=entries,
    )

"""
Does a nine actually earn more than a five?

This is the report the whole journal exists to produce. It groups measured
outcomes into score bands and asks, per band, what the median excess return
over ^GSPC was. If the bands come out in the wrong order — if the sevens beat
the nines — the scoring method is not working, and that is a thing the app
should be able to say about itself.

The honest part is `sufficient`
-------------------------------
For roughly the first six months every band will be empty, because the journal
only opened on 2026-08-23 and the shortest horizon is thirty days. A median of
three samples is not a finding, it is a coincidence with a decimal point, and
showing one would be the same defect this codebase keeps producing: an
absence rendered as a confident number.

So the threshold lives here, in the backend, not in the component that draws
the number. `sufficient` is a decision the API makes, and a caller that wants
to display a median from four samples has to ignore an explicit `false` to do
it. `first_result_expected` exists for the same reason — it turns "nothing
yet" into "the first answer arrives on this date", which is a different and
much more useful thing to tell someone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import Any, Final, Iterable, Sequence

from app.models.score_outcome import (
    STATUS_EVALUATED,
    STATUS_PENDING,
    STATUS_UNABLE,
)


#: Conviction bands, strongest first. Chosen to match how the app already
#: talks about scores: 9+ is the buy-guard tier, 7–8 is a real position, 4–6 is
#: a watch, 0–3 is a pass.
BANDS: Final[tuple[tuple[int, int, str], ...]] = (
    (9, 10, "9–10"),
    (7, 8, "7–8"),
    (4, 6, "4–6"),
    (0, 3, "0–3"),
)

#: Below this many measured outcomes in a band, no median is reported.
MIN_SAMPLE: Final[int] = 10


@dataclass(frozen=True)
class Measurement:
    """One outcome, reduced to what the report needs. Keeps this module pure."""

    conviction_score: int
    eval_status: str
    return_pct: Decimal | None = None
    excess_return_pct: Decimal | None = None
    expected_on: date | None = None


@dataclass
class BandReport:
    label: str
    score_min: int
    score_max: int
    n_evaluated: int = 0
    n_pending: int = 0
    n_unable: int = 0
    n_with_benchmark: int = 0
    median_excess_pct: Decimal | None = None
    median_return_pct: Decimal | None = None
    share_positive_excess: Decimal | None = None
    sufficient: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "score_min": self.score_min,
            "score_max": self.score_max,
            "n_evaluated": self.n_evaluated,
            "n_pending": self.n_pending,
            "n_unable": self.n_unable,
            "n_with_benchmark": self.n_with_benchmark,
            "median_excess_pct": _float(self.median_excess_pct),
            "median_return_pct": _float(self.median_return_pct),
            "share_positive_excess": _float(self.share_positive_excess),
            "sufficient": self.sufficient,
        }


@dataclass
class CalibrationReport:
    horizon_days: int
    min_sample: int
    sufficient: bool = False
    n_evaluated: int = 0
    n_pending: int = 0
    n_unable: int = 0
    first_result_expected: date | None = None
    bands: list[BandReport] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "horizon_days": self.horizon_days,
            "min_sample": self.min_sample,
            "sufficient": self.sufficient,
            "n_evaluated": self.n_evaluated,
            "n_pending": self.n_pending,
            "n_unable": self.n_unable,
            "first_result_expected": (
                self.first_result_expected.isoformat()
                if self.first_result_expected
                else None
            ),
            "bands": [band.as_dict() for band in self.bands],
        }


def calibrate(
    measurements: Iterable[Measurement],
    *,
    horizon_days: int,
    min_sample: int = MIN_SAMPLE,
) -> CalibrationReport:
    """
    Group outcomes into score bands and report each band's median.

    Pure. Every band is present in the output even when empty — a band that
    vanishes because it has no data reads as a band that does not exist.
    """
    rows = list(measurements)
    report = CalibrationReport(horizon_days=horizon_days, min_sample=min_sample)

    pending_dates = [
        row.expected_on
        for row in rows
        if row.eval_status == STATUS_PENDING and row.expected_on is not None
    ]
    report.first_result_expected = min(pending_dates) if pending_dates else None

    for low, high, label in BANDS:
        band = BandReport(label=label, score_min=low, score_max=high)
        in_band = [row for row in rows if low <= row.conviction_score <= high]

        band.n_evaluated = sum(1 for r in in_band if r.eval_status == STATUS_EVALUATED)
        band.n_pending = sum(1 for r in in_band if r.eval_status == STATUS_PENDING)
        band.n_unable = sum(1 for r in in_band if r.eval_status == STATUS_UNABLE)

        measured = [r for r in in_band if r.eval_status == STATUS_EVALUATED]
        excesses = [r.excess_return_pct for r in measured if r.excess_return_pct is not None]
        returns = [r.return_pct for r in measured if r.return_pct is not None]
        band.n_with_benchmark = len(excesses)

        band.sufficient = band.n_evaluated >= min_sample
        if band.sufficient:
            # Reported only above the threshold. Computing a median of four and
            # withholding it would be the same as not having it.
            if excesses:
                band.median_excess_pct = _median(excesses)
                band.share_positive_excess = _round(
                    Decimal(sum(1 for e in excesses if e > 0)) / Decimal(len(excesses))
                )
            if returns:
                band.median_return_pct = _median(returns)

        report.bands.append(band)
        report.n_evaluated += band.n_evaluated
        report.n_pending += band.n_pending
        report.n_unable += band.n_unable

    # The report as a whole is worth reading once any band can carry a median.
    report.sufficient = any(band.sufficient for band in report.bands)
    return report


def load_measurements(db, horizon_days: int) -> list[Measurement]:
    """Read one horizon's outcomes, joined to the score each one was measuring."""
    from app.models.score_history import ConvictionScoreHistory
    from app.models.score_outcome import ScoreOutcome

    rows = (
        db.query(
            ConvictionScoreHistory.conviction_score,
            ConvictionScoreHistory.recorded_at,
            ScoreOutcome.eval_status,
            ScoreOutcome.return_pct,
            ScoreOutcome.excess_return_pct,
        )
        .join(ScoreOutcome, ScoreOutcome.history_id == ConvictionScoreHistory.id)
        .filter(ScoreOutcome.horizon_days == horizon_days)
        .all()
    )

    return [
        Measurement(
            conviction_score=score,
            eval_status=status,
            return_pct=return_pct,
            excess_return_pct=excess,
            expected_on=_expected_on(recorded_at, horizon_days),
        )
        for score, recorded_at, status, return_pct, excess in rows
    ]


def _expected_on(recorded_at, horizon_days: int) -> date | None:
    """When a pending row becomes measurable."""
    if recorded_at is None:
        return None
    stamp = recorded_at.date() if hasattr(recorded_at, "date") else recorded_at
    return stamp + timedelta(days=horizon_days)


def _median(values: Sequence[Decimal]) -> Decimal:
    return _round(Decimal(str(median(values))))


def _round(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"))


def _float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)

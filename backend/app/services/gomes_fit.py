"""
„Sedí to k Markovi?" — a candidate placed against his actual entries.

Takes a ticker, computes what its chart looks like today with the same function
that built the reference distribution, and reports per feature whether that is
typical of a Mark Gomes entry, on the edge of one, or outside anything he has
done.

What this is not
----------------
It is not a verdict and must never become one. There is no score, no
recommendation, no word that can be read as "buy". The reason is not modesty:
the seven features here are everything that is in the PRICE, and what actually
makes Mark buy — he has spoken to management, read the 10-Q, knows the market
that company sells into — is not in the sheet and never will be. Matching the
shape of his entry without his research is cargo cult. That sentence is in the
rendered output, not just here.

What it is good for is the negative: "this is at its 52-week high on a quarter
of the liquidity he has ever touched" is a real thing to know before buying, and
nothing in the app said it before.

Honest arithmetic
-----------------
* Percentiles are not printed as numbers. Off forty entries, "82nd percentile"
  claims a precision the sample does not have. Three buckets plus the raw count
  of how many of his entries sat lower is what forty points support.
* A feature that cannot be computed is not counted. The summary says "five of
  seven, two could not be computed" rather than quietly dividing by five.
* Neighbour outcomes are never averaged. Three nearest cases are shown one by
  one with their distances; a mean of three returns would be exactly the kind
  of confident number this codebase exists to refuse.
"""

from __future__ import annotations

import json
import math
import pathlib
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

from app.services.entry_features import (
    FEATURE_LABELS_CS,
    PROFILE_FEATURES,
    Bar,
    Bars,
    EntryFeatures,
    FeatureError,
    compute,
    to_bars,
)

DATA: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parent.parent / "data"
PROFILE_PATH: Final[pathlib.Path] = DATA / "gomes_entry_profile.json"

#: The market-context feature. Reported as a share of his entries rather than a
#: bucket: it is a fact about the market, not about the company, and a quantile
#: there invites reading precision into a seven-point spread that is not in it.
GAUGE_FEATURE: Final[str] = "gauge_z_at_entry"

#: How many of his entries a candidate is shown alongside.
NEIGHBOURS: Final[int] = 3

#: Days of history to fetch. Enough for a 12-month window plus slack for halts.
FETCH_DAYS: Final[int] = 500

BUCKET_CS: Final[dict[str, str]] = {
    "TYPICKE": "TYPICKÉ",
    "NA_OKRAJI": "NA OKRAJI",
    "MIMO": "MIMO",
}

#: Printed under every profile. Not a disclaimer bolted on — the single most
#: important thing to know before acting on anything above it.
CAVEAT_CS: Final[str] = (
    "Co tohle NEŘÍKÁ: jestli akcie poroste. Mark kupuje po rozhovoru s vedením "
    "a přečteném 10-Q; z ceny se to poznat nedá. Tohle je kontrola tvaru, ne teze."
)


class FitError(Exception):
    """The candidate cannot be placed. Never a partial answer dressed as one."""


class _Unset:
    """
    Marks "the caller did not say" apart from "the caller said there is none".

    Needed because `market_z=None` has to mean the gauge is UNAVAILABLE — the
    index could not be read — and omitting it has to mean "go and read it". A
    plain `None` default collapses those two into one, and the collapse points
    the wrong way: an offline caller asking for no gauge would silently hit the
    network, and a genuine gauge failure would be indistinguishable from not
    having asked.
    """

    def __repr__(self) -> str:  # pragma: no cover — debugging courtesy
        return "<neuvedeno>"


UNSET: Final[_Unset] = _Unset()


# ==============================================================================
# The published profile
# ==============================================================================

@dataclass(frozen=True)
class Quantiles:
    n: int
    minimum: float
    p10: float
    p25: float
    median: float
    p75: float
    p90: float
    maximum: float

    def bucket(self, value: float) -> str:
        if self.p25 <= value <= self.p75:
            return "TYPICKE"
        if self.p10 <= value <= self.p90:
            return "NA_OKRAJI"
        return "MIMO"

    @property
    def iqr(self) -> float:
        return self.p75 - self.p25


@dataclass(frozen=True)
class ProfileEntry:
    row_id: int
    ticker: str
    entry_date: str
    exit_date: str
    exit_kind: str
    exit_reason: str
    note: str
    sheet_return_pct: float | None
    features: dict[str, float]


@dataclass(frozen=True)
class Profile:
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
        return bool(self.cohort.get("supports_neighbours", False))

    def count_below(self, feature: str, value: float) -> tuple[int, int]:
        """How many of his entries sat below this value, out of how many had it."""
        values = [
            e.features[feature] for e in self.entries if feature in e.features
        ]
        return sum(1 for v in values if v < value), len(values)


def load_profile(path: pathlib.Path = PROFILE_PATH) -> Profile:
    """
    The committed reference distribution.

    Raises rather than returning an empty profile: a fit report built on nothing
    would render seven cheerful "TYPICKÉ" rows.
    """
    if not path.exists():
        raise FitError(
            "Referenční profil Markových vstupů chybí "
            f"({path.name}). Vytvoří ho `python -m research.publish` z "
            "backend/."
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Profile(
        generated_at=raw["generated_at"],
        source=raw["source"],
        cohort=raw["cohort"],
        features={
            name: Quantiles(
                n=int(q["n"]), minimum=float(q["min"]), p10=float(q["p10"]),
                p25=float(q["p25"]), median=float(q["median"]),
                p75=float(q["p75"]), p90=float(q["p90"]), maximum=float(q["max"]),
            )
            for name, q in raw["features"].items()
        },
        entries=tuple(
            ProfileEntry(
                row_id=int(e["row_id"]), ticker=e["ticker"],
                entry_date=e["entry_date"], exit_date=e["exit_date"],
                exit_kind=e["exit_kind"], exit_reason=e["exit_reason"],
                note=e["note"], sheet_return_pct=e["sheet_return_pct"],
                features={k: float(v) for k, v in e["features"].items()},
            )
            for e in raw["entries"]
        ),
    )


# ==============================================================================
# One candidate
# ==============================================================================

@dataclass(frozen=True)
class FeatureFit:
    """One feature of the candidate against the cohort."""

    name: str
    label_cs: str
    value: float
    bucket: str
    quantiles: Quantiles
    #: How many of his entries sat below this value, and out of how many.
    below: int
    of: int

    @property
    def bucket_cs(self) -> str:
        return BUCKET_CS[self.bucket]


@dataclass(frozen=True)
class Neighbour:
    """One of Mark's entries this candidate resembles, and how closely."""

    entry: ProfileEntry
    distance: float
    #: Features both sides could supply — the distance is over these only.
    shared: tuple[str, ...]


@dataclass(frozen=True)
class Fit:
    """A candidate placed against the reference distribution."""

    ticker: str
    as_of: date
    features: EntryFeatures
    fits: tuple[FeatureFit, ...]
    #: Names of the profile features that could not be computed for this
    #: candidate. They are NOT in the denominator of the summary.
    uncomputable: tuple[str, ...]
    gauge_note_cs: str
    neighbours: tuple[Neighbour, ...]
    profile: Profile

    def count(self, bucket: str) -> int:
        return sum(1 for f in self.fits if f.bucket == bucket)

    @property
    def summary_cs(self) -> str:
        parts = [
            f"{self.count('MIMO')} mimo",
            f"{self.count('NA_OKRAJI')} na okraji",
            f"{self.count('TYPICKE')} typické",
        ]
        line = ", ".join(parts) + "."
        if self.uncomputable:
            labels = ", ".join(
                FEATURE_LABELS_CS.get(n, n).lower() for n in self.uncomputable
            )
            line += f" Nešlo spočítat: {labels}."
        return line


def _standardised_distance(
    candidate: dict[str, float],
    entry: ProfileEntry,
    quantiles: dict[str, Quantiles],
) -> tuple[float, tuple[str, ...]] | None:
    """
    Euclidean distance over the features both sides have, scaled by the IQR.

    IQR rather than standard deviation: the cohort holds a $3 000 000-a-day name
    next to a $40 000-a-day one, and a spread statistic that a single outlier can
    move would make every candidate look equidistant from everything.
    """
    total = 0.0
    shared: list[str] = []
    for name, value in candidate.items():
        theirs = entry.features.get(name)
        spread = quantiles[name].iqr if name in quantiles else 0.0
        if theirs is None or spread <= 0:
            continue
        total += ((value - theirs) / spread) ** 2
        shared.append(name)
    if len(shared) < 3:
        return None
    return math.sqrt(total / len(shared)), tuple(shared)


def fetch_bars(ticker: str, *, as_of: date | None = None) -> Bars:
    """
    Daily bars for a candidate, split-adjusted, with the intraday range.

    Same call shape as `research/prices.py`, so the reference distribution and a
    candidate are read off the same kind of series. `score_outcomes` cannot be
    reused: it keeps only the close, and half these features are about the range
    and the volume.

    Every known symbol for the company is tried, US OTC form first, via
    `app/core/tickers.py`. Four of this portfolio's positions are held on a
    Canadian exchange under a symbol the data source does not answer to —
    `KUYA.V` returns nothing while `KUYAF` returns six years — and refusing them
    would mean the tool went quiet on exactly the holdings it was asked about.
    Which symbol actually answered is reported, not hidden: `Bars.ticker` is the
    one that worked.
    """
    from app.core.tickers import variants_of

    end = as_of or date.today()
    start = end - timedelta(days=FETCH_DAYS)
    attempts = variants_of(ticker) or (ticker,)
    failures: list[str] = []

    for symbol in attempts:
        try:
            frame = _history(symbol, start, end)
        except FitError as exc:
            failures.append(str(exc))
            continue
        if frame is not None and not frame.empty:
            return _to_bars(symbol, frame)

    tried = ", ".join(attempts)
    raise FitError(
        f"{ticker}: zdroj nemá kurzy pod žádným známým symbolem ({tried}). "
        f"Buď se pod ním neobchoduje, nebo je zapsaný jinak."
        + (f" Navíc: {failures[0]}" if failures else "")
    )


def _history(symbol: str, start: date, end: date):
    try:
        import yfinance as yf

        return yf.Ticker(symbol).history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
            actions=True,
        )
    except Exception as exc:  # noqa: BLE001
        raise FitError(f"{symbol}: kurzy se nepodařilo stáhnout — {exc}") from exc


def _to_bars(ticker: str, frame) -> Bars:
    if "Adj Close" not in frame:
        raise FitError(
            f"{ticker}: v odpovědi chybí 'Adj Close' — bez něj nejde odlišit "
            f"kurz z toho dne od zpětně přepočteného"
        )

    rows: list[Bar] = []
    for stamp, row in frame.iterrows():
        close = row["Close"]
        if close != close:
            continue
        rows.append(
            Bar(
                day=stamp.date(), open=float(row["Open"]), high=float(row["High"]),
                low=float(row["Low"]), close=float(close),
                adj_close=float(row["Adj Close"]),
                volume=int(row["Volume"]) if row["Volume"] == row["Volume"] else 0,
                split=float(row.get("Stock Splits", 0.0) or 0.0),
            )
        )
    return to_bars(ticker, rows)


def gauge_z(as_of: date | None = None) -> float | None:
    """Where the index sits, or None. A missing gauge is never a zero."""
    from app.services.market_gauge import GaugeError, fetch_series, fit

    try:
        return fit(fetch_series(), as_of=as_of).z_score
    except (GaugeError, Exception):  # noqa: BLE001 — any failure is the same absence
        return None


def fit_candidate(
    ticker: str,
    *,
    as_of: date | None = None,
    profile: Profile | None = None,
    bars: Bars | None = None,
    market_z: float | None | _Unset = UNSET,
) -> Fit:
    """
    Place one candidate against Mark's entries.

    `bars` and `market_z` are injectable so this is testable without a network.
    Omitting `market_z` fetches the index reading; passing `None` states that
    there is not one, and the report then says so instead of implying a neutral
    market. Those are different facts and the signature keeps them apart.
    """
    reference = profile or load_profile()
    when = as_of or date.today()
    series = bars if bars is not None else fetch_bars(ticker, as_of=when)

    try:
        features = compute(series, series.last_day or when)
    except FeatureError as exc:
        raise FitError(str(exc)) from exc

    z = gauge_z(when) if isinstance(market_z, _Unset) else market_z

    values: dict[str, float] = {}
    fits: list[FeatureFit] = []
    uncomputable: list[str] = []

    for name in PROFILE_FEATURES:
        value = features.get(name)
        quantiles = reference.features.get(name)
        if value is None or quantiles is None:
            uncomputable.append(name)
            continue
        values[name] = value
        below, of = reference.count_below(name, value)
        fits.append(
            FeatureFit(
                name=name, label_cs=FEATURE_LABELS_CS.get(name, name),
                value=value, bucket=quantiles.bucket(value),
                quantiles=quantiles, below=below, of=of,
            )
        )

    if z is None:
        gauge_note = (
            "Semafor (z-skóre S&P): nešlo spočítat — bez něj nevím, v jakém "
            "trhu by se kupovalo."
        )
    else:
        values[GAUGE_FEATURE] = z
        quantiles = reference.features.get(GAUGE_FEATURE)
        at_or_above = 0
        of = 0
        if quantiles:
            at_or_above, of = _share_at_or_above(reference, GAUGE_FEATURE, z)
        gauge_note = (
            f"Semafor (z-skóre S&P): {z:+.2f}. "
            f"Mark vstupoval při z ≥ {z:+.2f} v {at_or_above} ze {of} případů."
        )

    neighbours: list[Neighbour] = []
    if reference.supports_neighbours and len(values) >= 3:
        scored = []
        for entry in reference.entries:
            measured = _standardised_distance(values, entry, reference.features)
            if measured is not None:
                scored.append(Neighbour(entry, measured[0], measured[1]))
        neighbours = sorted(scored, key=lambda n: n.distance)[:NEIGHBOURS]

    return Fit(
        ticker=ticker, as_of=when, features=features, fits=tuple(fits),
        uncomputable=tuple(uncomputable), gauge_note_cs=gauge_note,
        neighbours=tuple(neighbours), profile=reference,
    )


def _share_at_or_above(
    profile: Profile, feature: str, threshold: float
) -> tuple[int, int]:
    values = [
        e.features[feature] for e in profile.entries if feature in e.features
    ]
    return sum(1 for v in values if v >= threshold), len(values)


# ==============================================================================
# Rendering
# ==============================================================================

def _number(name: str, value: float) -> str:
    if name == "median_dollar_volume_20d":
        return f"{value / 1_000_000:.2f} M$"
    if name == "price_level":
        return f"{value:.2f} $"
    return f"{value:+.0f} %"


def render_cs(fit: Fit) -> str:
    """The whole report as a person reads it. No verdict word anywhere."""
    cohort = fit.profile.cohort
    lines = [
        # %-d is glibc-only and this runs on Windows.
        f"{fit.ticker} — profil vstupu k "
        f"{fit.as_of.day}. {fit.as_of.month}. {fit.as_of.year}",
        f"Srovnáno s {fit.profile.n_rows} Markovými vstupy "
        f"{cohort.get('first_entry', '')[:4]}–{cohort.get('last_entry', '')[:4]} "
        f"({fit.profile.n_tickers} různých firem)",
        "",
    ]
    for item in fit.fits:
        lines.append(
            f"  {item.label_cs:26s} {_number(item.name, item.value):>12s}   "
            f"Mark: medián {_number(item.name, item.quantiles.median):>10s}   "
            f"{item.bucket_cs:9s} ({item.below} z {item.of} níž)"
        )
    lines += ["", f"  {fit.gauge_note_cs}", "", f"  {fit.summary_cs}"]

    if fit.neighbours:
        lines += ["", "Tvarově nejblíž má k:"]
        for neighbour in fit.neighbours:
            entry = neighbour.entry
            result = (
                f"{entry.sheet_return_pct:+.0f} %"
                if entry.sheet_return_pct is not None else "—"
            )
            state = "otevřeno" if not entry.exit_date else "konec"
            lines.append(
                f"  {entry.ticker:6s} {entry.entry_date}  "
                f"vzdálenost {neighbour.distance:.2f}  {state} {result}"
            )
            if entry.note:
                lines.append(f"         „{entry.note[:88]}“")
        lines.append(
            "  (tři případy jsou historka, ne důkaz — výnosy se záměrně "
            "neprůměrují)"
        )
    elif not fit.profile.supports_neighbours:
        lines += [
            "",
            "Nejpodobnější vstupy se neukazují: profil stojí na méně než "
            "40 vstupech a tři nejbližší z nich by byly náhoda s desetinnou čárkou.",
        ]

    lines += ["", CAVEAT_CS]
    return "\n".join(lines)

"""
What a company said about itself, in the only form the rubric may use.

The gap this fills
------------------
Four holdings file in Canada — 54 % of the portfolio by value — so EDGAR has
nothing on them and `cylinders.propose_cylinders` falls to Yahoo's trailing
aggregates, from which no year-on-year quarter comparison exists. The companies
do publish the comparison, in their own quarterly releases. `app/data/
company_releases.json` holds what those releases actually say, read by hand from
pages fetched through `services/firecrawl.py`.

Why this is a curated file and not a parser
-------------------------------------------
This app deleted `price_lines_data.py` for being exactly this shape: numbers in
a committed file that nothing could trace back to a source. The difference has
to be provenance, so it is enforced rather than intended — a reading without a
verbatim quote, a period end and a source URL is dropped here and never reaches
the rubric. What survives can always be checked against the sentence it came
from.

Two rules that look like caution and are actually correctness
------------------------------------------------------------
**Only currency-neutral readings score.** Three of the four releases write `$`
without ever saying which dollar. A percentage change, a margin in points and
the sign of a result are all immune to that; an absolute figure is not. So
absolute amounts are kept as `context` for a human to read and are never
arithmetic. This is the same trap that produced a wrong TRIM on GSI.V.

**The percentage is the company's, not ours.** Every ratio here is quoted from
the release rather than computed from two absolute numbers, because choosing
the base is choosing the answer — and a nine-month figure divided by a
three-month one is how growth becomes collapse.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from loguru import logger

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "company_releases.json"

#: Accounting result, which is not cash generation and is never presented as
#: it. A mine ramping up can report a widening loss while funding itself, and a
#: company can report a profit made of a deferred tax asset — D-BOX did exactly
#: that this quarter.
PROFIT = "PROFIT"
LOSS = "LOSS"

#: Balance-sheet states. Comparisons rather than amounts, so they survive a
#: release that never names its currency.
CASH_EXCEEDS_DEBT = "CASH_EXCEEDS_DEBT"
DEBT_EXCEEDS_CASH = "DEBT_EXCEEDS_CASH"
BALANCED = "BALANCED"

_WORD_VALUES = frozenset(
    {PROFIT, LOSS, CASH_EXCEEDS_DEBT, DEBT_EXCEEDS_CASH, BALANCED}
)


@dataclass(frozen=True)
class Reading:
    """One number, the sentence it came from, and the span it covers."""

    value: float | str
    basis_months: int
    quote: str
    prior: float | None = None


@dataclass(frozen=True)
class Publication:
    """
    A day, or only a month, on which the company actually published a report.

    The distinction is the point. Gatekeeper's own IR page dates its statements
    to the month it uploaded them and no further; Kuya's press releases carry
    the day in the URL. An estimate built on the first must say "December", not
    "15 December" — precision nobody has is the failure mode this app keeps
    finding.
    """

    label: str
    year: int
    month: int
    #: None when the source only knew the month.
    day: int | None = None

    @property
    def exact(self) -> bool:
        return self.day is not None


@dataclass(frozen=True)
class Release:
    """
    One quarterly release, reduced to what may be scored.

    `absent` is load-bearing: it is the list of things the release does not say,
    and it is what stops the rubric from treating a silence as a zero.
    """

    ticker: str
    company: str
    fiscal_label: str
    period_end: date
    published: date
    source_url: str
    currency: str | None
    currency_note: str
    readings: dict[str, Reading]
    context: tuple[str, ...] = ()
    absent: tuple[str, ...] = ()
    #: When this company has actually published results before. Used to say
    #: when the next one is due for companies no provider covers.
    publications: tuple[Publication, ...] = ()
    publications_note: str = ""

    @property
    def has_anything(self) -> bool:
        return bool(self.readings)


def _parse_date(value: Any) -> date | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _reading(name: str, raw: Any, *, ticker: str) -> Reading | None:
    """
    One reading, or nothing — with the reason logged rather than guessed at.

    A null is the normal case and means the release did not say. A dict missing
    its quote is the dangerous case: a number nobody can check, which is what
    this module exists to refuse.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        logger.warning("company_releases: {} {} není objekt, zahazuji", ticker, name)
        return None

    quote = str(raw.get("quote") or "").strip()
    if not quote:
        logger.warning(
            "company_releases: {} {} je bez doslovné citace, zahazuji", ticker, name
        )
        return None

    value = raw.get("value")
    if value is None:
        return None
    if isinstance(value, str):
        if value.upper() not in _WORD_VALUES:
            logger.warning(
                "company_releases: {} {} má neznámou hodnotu {!r}", ticker, name, value
            )
            return None
        value = value.upper()
    else:
        try:
            value = float(value)
        except (TypeError, ValueError):
            logger.warning("company_releases: {} {} není číslo", ticker, name)
            return None

    basis = raw.get("basis_months")
    try:
        basis = int(basis)
    except (TypeError, ValueError):
        logger.warning(
            "company_releases: {} {} neuvádí délku období, zahazuji", ticker, name
        )
        return None

    prior = raw.get("prior")
    try:
        prior = None if prior is None else float(prior)
    except (TypeError, ValueError):
        prior = None

    return Reading(value=value, basis_months=basis, quote=quote, prior=prior)


def _publication(raw: Any) -> Publication | None:
    """One past publication, at whatever precision the source actually had."""
    if not isinstance(raw, dict):
        return None
    text = str(raw.get("published") or "").strip()
    match = re.fullmatch(r"(\d{4})-(\d{2})(?:-(\d{2}))?", text)
    if match is None:
        logger.warning("company_releases: datum zveřejnění {!r} nerozumím", text)
        return None
    year, month, day = match.groups()
    return Publication(
        label=str(raw.get("label") or ""),
        year=int(year),
        month=int(month),
        day=int(day) if day else None,
    )


def _release(raw: dict[str, Any]) -> Release | None:
    ticker = str(raw.get("ticker") or "").strip().upper()
    period_end = _parse_date(raw.get("period_end"))
    published = _parse_date(raw.get("published"))
    url = str(raw.get("source_url") or "").strip()

    # Provenance is the whole difference between this file and the one that got
    # deleted. Anything that cannot be traced back does not exist.
    if not ticker or period_end is None or not url.startswith("http"):
        logger.warning(
            "company_releases: záznam bez tickeru, období nebo zdroje — vynechán"
        )
        return None

    readings = {}
    for name, value in (raw.get("readings") or {}).items():
        parsed = _reading(name, value, ticker=ticker)
        if parsed is not None:
            readings[name] = parsed

    return Release(
        ticker=ticker,
        company=str(raw.get("company") or ticker),
        fiscal_label=str(raw.get("fiscal_label") or ""),
        period_end=period_end,
        published=published or period_end,
        source_url=url,
        currency=(raw.get("currency") or None),
        currency_note=str(raw.get("currency_note") or ""),
        readings=readings,
        context=tuple(raw.get("context") or ()),
        absent=tuple(raw.get("absent") or ()),
        publications=tuple(
            p
            for p in (
                _publication(item)
                for item in ((raw.get("publication_history") or {}).get("publications") or [])
            )
            if p is not None
        ),
        publications_note=str((raw.get("publication_history") or {}).get("note") or ""),
    )


@lru_cache(maxsize=1)
def _load(path_text: str) -> dict[str, Release]:
    path = Path(path_text)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("company_releases: soubor nejde přečíst ({})", type(exc).__name__)
        return {}

    out: dict[str, Release] = {}
    for item in raw.get("releases") or []:
        release = _release(item)
        if release is None:
            continue
        # Newest wins, so adding next quarter's release above or below the old
        # one makes no difference.
        existing = out.get(release.ticker)
        if existing is None or release.period_end > existing.period_end:
            out[release.ticker] = release
    return out


def load_all(*, path: Path | None = None) -> dict[str, Release]:
    """Every company's latest release, keyed by the US-style ticker."""
    return _load(str(path or DATA_FILE))


def for_ticker(ticker: str, *, path: Path | None = None) -> Release | None:
    """
    The latest release for one company, across its listings.

    Goes through `variants_of` for the same reason every other lookup in this
    app does: the position is held as `KUYA.V` and the file is keyed `KUYAF`.
    """
    from app.core.tickers import variants_of

    releases = load_all(path=path)
    for symbol in variants_of(ticker) or (ticker.upper(),):
        found = releases.get(symbol.upper())
        if found is not None:
            return found
    return None

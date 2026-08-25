"""
Gathering what the cylinder rubric reads, and recording what the owner confirms.

`app/services/cylinders.py` is deliberately pure — the same inputs give the same
number, with no clock, no network and no Session. This module is the other half:
it collects those inputs from wherever they live, and it writes the confirmed
result back.

The split matters because the rubric's rules are the part worth arguing about,
and rules that need a database to exercise do not get argued with.

The confirmation step
---------------------
A proposal never authorises anything. `stock_lifecycle.cylinders_count` is only
written when the owner has looked at the evidence and said yes, and the Buy
Guard reads only a confirmed value. Without that rule the rubric would be the
same invented input as before, moved one storey up: a number nobody checked,
sized by thresholds nobody validated, authorising purchases with real money.

Confirmations expire. A cylinder count describes how a company is operating,
and the next quarterly report is exactly the event that can make it wrong, so
`valid_until` is set to a quarter ahead unless the caller knows the real date.
An expired confirmation is not deleted: the selling side keeps reading it,
because stale data may make this app more cautious and never less.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from typing import Any

from loguru import logger
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.czech import d as cz_date
from app.core.sources import (
    RANK_RUBRIC,
    InvestmentSource,
    lifecycle_source_rank,
    verdict_stance,
)
from app.core.tickers import canonical_ticker, variants_of
from app.models.gomes import StockLifecycleModel
from app.models.sec import InsiderTransaction, SecCoverage
from app.models.stock import Stock
from app.services import release_fundamentals
from app.services.cylinders import CylinderProposal, QualityInputs, propose_cylinders

#: How far back an open-market insider trade still says something. Six months
#: is the window the app already uses to call insider activity "recent"; older
#: than that and it describes a different company.
INSIDER_WINDOW = timedelta(days=180)

#: How long the analyst's own read counts. The same half-life the claim
#: extraction already applies to `ticker_mentions`.
ANALYST_WINDOW = timedelta(days=180)

#: A confirmation lasts until the next report can contradict it. Used only when
#: the caller does not know the real earnings date — which is today's case, so
#: the value is a fallback and is labelled as one wherever it is shown.
DEFAULT_VALIDITY = timedelta(days=95)

SOURCE_RUBRIC = "rubric"

#: `stock_lifecycle.confidence` is constrained to HIGH / MEDIUM / LOW and is
#: shared with the keyword lifecycle classifier. The rubric's own labels are
#: Czech because they are shown to the owner; they are translated at this
#: boundary rather than widening a constraint that other writers rely on.
#: The database refused the untranslated value outright, which is the schema
#: doing its job — a column whose vocabulary drifts per writer is one nothing
#: downstream can group by.
_CONFIDENCE_TO_COLUMN = {"VYSOKA": "HIGH", "STREDNI": "MEDIUM", "NIZKA": "LOW"}


@dataclass(frozen=True)
class Confirmation:
    """What the owner agreed to, and what he was looking at when he did."""

    ticker: str
    cylinders: int
    confirmed_by: str
    valid_until: datetime | None
    phase: str


def gather(db: Session, ticker: str, *, as_of: date | None = None) -> QualityInputs:
    """
    Assemble everything the rubric reads for one company.

    Never fetches from the network. SEC fundamentals are the one input this
    cannot supply — reading XBRL is an HTTP call per company, and the caller
    decides whether to pay for it — so `fundamentals` is passed in separately
    by whoever has it. What is here is what the database already knows.
    """
    day = as_of or datetime.now(timezone.utc).date()
    symbols = variants_of(ticker) or (ticker.upper(),)

    return QualityInputs(
        ticker=ticker.upper(),
        as_of=day,
        release=release_fundamentals.for_ticker(ticker),
        yahoo=_yahoo_aggregates(db, symbols),
        analyst_stance=_analyst_stance(db, symbols, day),
        **_filing_findings(db, symbols),
        **_insider_counts(db, symbols, day),
    )


def is_sec_covered(db: Session, ticker: str) -> bool:
    """
    Whether EDGAR can see this company at all.

    Four distinct absences hide behind a "no" here — not an SEC filer, an ISIN
    where a ticker should be, a foreign private issuer filing 20-F, and EDGAR
    simply unreachable — and only the first three are facts about the company.
    The rubric does not need to tell them apart; it needs to know not to expect
    audited quarterly numbers.
    """
    row = (
        db.query(SecCoverage)
        .filter(SecCoverage.ticker.in_(variants_of(ticker) or (ticker.upper(),)))
        .first()
    )
    return bool(row and row.status == "COVERED" and row.cik)


def _yahoo_aggregates(db: Session, symbols: tuple[str, ...]) -> dict[str, Any] | None:
    """
    Trailing-twelve-month figures from the quote cache.

    This is the layer that reaches the Canadian and OTC names EDGAR cannot see
    — four of the five largest positions. Unaudited and trendless, which is why
    the rubric clamps anything built on it away from the ends of the scale.
    """
    from sqlalchemy import text

    for symbol in symbols:
        try:
            row = db.execute(
                text(
                    "SELECT profit_margin, operating_margin, total_cash, total_debt, "
                    "revenue_ttm, net_income_ttm FROM yahoo_finance_cache "
                    "WHERE ticker = :t"
                ),
                {"t": symbol},
            ).fetchone()
        except Exception:  # noqa: BLE001 — a missing cache table is not a crash
            logger.exception("Yahoo cache pro {} se nepodařilo přečíst", symbol)
            return None

        if row is None:
            continue
        data = dict(row._mapping)
        if any(v is not None for v in data.values()):
            return data
    return None


def _insider_counts(db: Session, symbols: tuple[str, ...], day: date) -> dict[str, Any]:
    """
    Open-market purchases and sales in the recent window.

    Reads `signal`, which the Form 4 parser derives from the SEC transaction
    code and never from acquired/disposed. The first Form 4 this app ever read
    was a gift of 8,000 shares at $0.00 flagged as a disposal; counting that as
    an insider selling would have been a fact about nothing.

    `insider_data_available` separates "nobody traded" from "we have no Form 4
    data for this company" — the second is a gap and has to say so.
    """
    since = day - INSIDER_WINDOW

    rows = (
        db.query(InsiderTransaction)
        .filter(InsiderTransaction.ticker.in_(symbols))
        .all()
    )
    if not rows:
        return {"insider_data_available": False}

    recent = [
        r for r in rows
        if r.transaction_date is not None and r.transaction_date >= since
    ]
    return {
        "insider_data_available": True,
        "insider_buys": sum(1 for r in recent if r.signal == "BUY"),
        "insider_sells": sum(1 for r in recent if r.signal == "SELL"),
    }


def _analyst_stance(db: Session, symbols: tuple[str, ...], day: date) -> str | None:
    """
    What Gomes last said about the company, reduced to a direction.

    Only the GOMES source: the Breakout watchlist is a scraped list, not a
    stance, and the named-analyst roster does not exist yet. Older than the
    window it describes a company that has since reported twice.
    """
    row = (
        db.query(Stock)
        .filter(Stock.ticker.in_(symbols))
        .filter(Stock.source_key == InvestmentSource.GOMES.value)
        .filter(Stock.action_verdict.isnot(None))
        .order_by(desc(Stock.created_at))
        .first()
    )
    if row is None:
        return None
    if row.created_at is not None and row.created_at.date() < day - ANALYST_WINDOW:
        return None

    stance = verdict_stance(row.action_verdict)
    return None if stance == "NEUTRAL" else stance


def propose(
    db: Session,
    ticker: str,
    *,
    fundamentals=None,
    as_of: date | None = None,
) -> CylinderProposal:
    """One company's proposal, from the database plus whatever XBRL the caller has."""
    inputs = gather(db, ticker, as_of=as_of)
    if fundamentals is not None:
        # `replace` rather than a fresh QualityInputs: the field list here used
        # to be written out by hand and had silently stopped carrying
        # `filing_findings` / `filings_read`, so every company the caller had
        # XBRL for — which is every SEC filer — lost its going-concern warnings
        # on the way in. `_from_findings` then reported them as unread. SMSI and
        # ECOR, the two names that rule exists for, were both affected.
        inputs = replace(inputs, fundamentals=fundamentals)
    return propose_cylinders(inputs)


def confirm(
    db: Session,
    ticker: str,
    cylinders: int,
    *,
    confirmed_by: str,
    proposal: CylinderProposal | None = None,
    valid_until: datetime | None = None,
    phase: str | None = None,
    now: datetime | None = None,
    override: bool = False,
) -> StockLifecycleModel:
    """
    Record a cylinder count the owner has agreed to.

    This is the only path that produces a number the Buy Guard will accept. It
    supersedes the previous active row rather than editing it, so what the app
    believed last quarter stays readable — the same append-only discipline the
    score journal keeps, and for the same reason: a decision is a claim made at
    a moment and is never rewritten.

    `phase` carries the lifecycle stage forward when the caller knows it. When
    it does not, the previous row's stage is kept rather than reset to UNKNOWN,
    because forgetting that a company is in Wait Time would silently unblock a
    purchase the canon forbids (§3).
    """
    if not 0 <= cylinders <= 10:
        raise ValueError(f"Válce musí být 0-10, dostal jsem {cylinders}")

    moment = now or datetime.now(timezone.utc)
    symbol = canonical_ticker(ticker) or ticker.upper()

    previous = (
        db.query(StockLifecycleModel)
        .filter(StockLifecycleModel.ticker == symbol)
        .filter(StockLifecycleModel.valid_until.is_(None))
        .order_by(desc(StockLifecycleModel.detected_at))
        .first()
    )

    # An estimate does not get to close out a statement by being newer.
    #
    # This row is written with `source = rubric`, and the row it would replace
    # may be Gomes on record. On 2026-08-23 that is exactly what happened to
    # Gatekeeper: his „all ten cylinders" from two days earlier was superseded
    # by a rubric 5, the deserved bar moved 0 -> 5, and the engine ordered half
    # the position sold. Nobody chose that; the writer simply preferred the
    # newest row.
    #
    # The owner keeps the last word — `override=True` is his, and the caller
    # has to ask for it, which means the screen has to show him what he is
    # overwriting first. What is gone is the accidental path.
    if previous is not None and not override:
        standing = _outranks_rubric(previous, moment)
        if standing is not None:
            raise ValueError(standing)

    if previous is not None:
        previous.valid_until = moment

    resolved_phase = phase or (previous.phase if previous is not None else None) or "UNKNOWN"

    row = StockLifecycleModel(
        ticker=symbol,
        phase=resolved_phase,
        is_investable=resolved_phase != "WAIT_TIME",
        cylinders_count=cylinders,
        firing_on_all_cylinders=cylinders >= 10,
        phase_signals=_override_note(
            _evidence_payload(proposal), previous, override
        ),
        phase_reasoning=(proposal.summary_cs() if proposal is not None else None),
        confidence=(
            _CONFIDENCE_TO_COLUMN.get(proposal.confidence)
            if proposal is not None else None
        ),
        source=SOURCE_RUBRIC,
        detected_at=moment,
        cylinders_confirmed_at=moment,
        cylinders_confirmed_by=confirmed_by,
        cylinders_valid_until=valid_until or (moment + DEFAULT_VALIDITY),
    )
    db.add(row)
    logger.info("Válce {} potvrzeny na {} ({})", symbol, cylinders, confirmed_by)
    return row


def _override_note(
    payload: dict[str, Any],
    previous: StockLifecycleModel | None,
    override: bool,
) -> dict[str, Any]:
    """
    Stamp the evidence when the owner knowingly overruled a stronger source.

    Without this the new row looks exactly like any other rubric confirmation,
    and a year from now nobody can tell that Gomes had said something else. His
    call stands either way; it just has to leave a mark.
    """
    if not (override and previous is not None):
        return payload
    if lifecycle_source_rank(previous.source) <= RANK_RUBRIC:
        return payload
    payload = dict(payload)
    payload["overrode_source"] = previous.source
    payload["overrode_cylinders"] = previous.cylinders_count
    payload["overrode_detected_at"] = (
        previous.detected_at.isoformat() if previous.detected_at else None
    )
    return payload


def _aware(moment: datetime | None) -> datetime | None:
    """UTC-aware, whatever the driver handed back."""
    if moment is None:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


def _outranks_rubric(
    previous: StockLifecycleModel, moment: datetime
) -> str | None:
    """
    Why the live row must not be superseded by a rubric write, in Czech.

    Returns None when the rubric may proceed — the live row is another rubric
    reading, or it is an analyst reading old enough that the next report has
    already had its chance to contradict it.

    The message is the whole point of the guard, so it names the source, the
    number and the date. „Nelze zapsat" with no reason would just be a wall.
    """
    if lifecycle_source_rank(previous.source) <= RANK_RUBRIC:
        return None

    expiry = _aware(previous.cylinders_valid_until)
    if expiry is None:
        # No expiry recorded: a spoken cylinder count stands until the next
        # report can contradict it, which is the same quarter this module
        # already grants a confirmation.
        detected = _aware(previous.detected_at)
        expiry = (detected + DEFAULT_VALIDITY) if detected is not None else None
    if expiry is not None and expiry <= moment:
        return None

    said = _aware(previous.detected_at)
    when = f" z {cz_date(said)}" if said is not None else ""
    count = previous.cylinders_count
    number = f"{count} válců" if count is not None else "svůj údaj o válcích"

    return (
        f"{previous.ticker}: platí {number}{when} ze zdroje "
        f"„{previous.source}“ — odhad aplikace to nepřepíše. "
        f"Když to chceš přesto změnit, potvrď s override=true; "
        f"zapíše se, že jsi vědomě přebil silnější zdroj."
    )


def _evidence_payload(proposal: CylinderProposal | None) -> dict[str, Any]:
    """
    The evidence, stored beside the number it produced.

    Without it the confirmation is just a digit and nobody — including the
    owner three months later — can tell whether it was justified.
    """
    if proposal is None:
        return {}
    return {
        "layer": proposal.layer,
        "confidence": proposal.confidence,
        "proposed": proposal.cylinders,
        # Stored as a number, not only inside a sentence. Survival is the one
        # rule that still works for a company the method cannot value, and a
        # figure trapped in prose is one nothing downstream can read.
        "runway_months": proposal.runway_months,
        "runway_as_of": (
            proposal.runway_as_of.isoformat() if proposal.runway_as_of else None
        ),
        "evidence": [
            {
                "delta": e.delta,
                "fact_cs": e.fact_cs,
                "source": e.source,
                "as_of": e.as_of.isoformat() if e.as_of else None,
            }
            for e in proposal.evidence
        ],
        "unknowns": list(proposal.unknowns),
    }


#: Structured findings started being written on this date. Eight filings were
#: analysed before it and their warnings exist only as Czech prose, so a filing
#: read earlier must NOT be treated as read here — "no findings" would then be
#: a clean bill of health for SMSI, whose going concern is sitting in that very
#: markdown. Re-reading them would spend API credit on work the subscription
#: covers; until somebody does, they count as unread.
FINDINGS_STRUCTURED_SINCE = datetime(2026, 8, 23, tzinfo=timezone.utc)


def _filing_findings(db: Session, symbols: tuple[str, ...]) -> dict[str, Any]:
    """
    Material warnings from the newest filing read since findings were stored.

    Only the newest: an older filing's warnings are a fact about that quarter,
    not about today, and counting a going concern twice because it appeared in
    two consecutive reports would double a penalty the company earned once.

    `filings_read` separates "nothing material" from "nobody has opened it",
    and the cutover date is what stops an analysis written before this table
    existed from masquerading as the first.
    """
    from app.models.sec import SecFiling
    from app.models.sec_finding import SEVERITY_ORDER, SecFinding

    analysed = (
        db.query(SecFiling)
        .filter(SecFiling.ticker.in_(symbols))
        .filter(SecFiling.analysis.isnot(None))
        .filter(SecFiling.analyzed_at.isnot(None))
        .filter(SecFiling.analyzed_at >= FINDINGS_STRUCTURED_SINCE)
        .order_by(desc(SecFiling.filed_date))
        .first()
    )
    if analysed is None:
        return {"filings_read": False, "filing_findings": ()}

    rows = (
        db.query(SecFinding)
        .filter(SecFinding.accession == analysed.accession)
        .all()
    )
    ordered = sorted(rows, key=lambda r: SEVERITY_ORDER.get(r.severity, 9))
    return {
        "filings_read": True,
        "filing_findings": tuple((r.severity, r.fact_cs) for r in ordered),
    }

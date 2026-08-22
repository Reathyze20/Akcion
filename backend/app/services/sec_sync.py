"""
Pulling SEC data for held positions and storing it.

Ties `sec_edgar` (filings, Form 4) and `sec_fundamentals` (XBRL results,
narrative outlook) together and persists the result, so the app can show what
the regulator says without going to the network on every page load.

Order of importance, and it is deliberate: **results and outlook first**.
Insider transactions are stored because they are cheap to collect and
occasionally telling, but they are the footnote. The canon is a fundamental
method — §4a builds the whole risk/reward chart out of revenue growth and
margin expectations — so what the company earned and what it says comes next
is the signal, and who bought stock last week is trivia by comparison.

Every path here keeps "we did not look", "we looked and there is nothing" and
"this company does not file here" as three different answers.
"""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Final

from loguru import logger
from sqlalchemy.orm import Session

from app.models.sec import InsiderTransaction as InsiderTransactionRow
from app.models.sec import SecCoverage, SecFiling
from app.services.sec_edgar import (
    CoverageStatus,
    SecEdgarClient,
    SecError,
    TickerCoverage,
)
from app.services.sec_fundamentals import (
    Fundamentals,
    analyze_outlook,
    fetch_fundamentals,
)

#: Filing text beyond this is truncated. A 10-Q renders to roughly 120,000
#: characters, so this leaves headroom for a long 10-K without ever sending an
#: unbounded document. Truncation is reported, never silent.
MAX_FILING_CHARS: Final[int] = 400_000


@dataclass
class SyncResult:
    """What one refresh did, per ticker."""

    ticker: str
    status: str
    company_name: str | None = None
    filings_stored: int = 0
    insider_stored: int = 0
    findings: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    note: str | None = None
    error: str | None = None


# ==============================================================================
# Filing text
# ==============================================================================

def extract_text(html: str) -> tuple[str, bool]:
    """
    Turn a filing's HTML into readable text.

    Returns (text, truncated). Truncation is returned rather than hidden,
    because a guidance sentence that fell off the end is indistinguishable
    from a company that gave no guidance — and those must not look alike.
    """
    without_code = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?is)<(br|/p|/div|/tr)[^>]*>", "\n", without_code)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)

    # Filings use typographic quotes and non-breaking spaces throughout;
    # normalising them is what makes any later text matching survive.
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()

    if len(text) > MAX_FILING_CHARS:
        return text[:MAX_FILING_CHARS], True
    return text, False


# ==============================================================================
# Persistence
# ==============================================================================

def _upsert_coverage(
    db: Session,
    coverage: TickerCoverage,
) -> SecCoverage:
    row = (
        db.query(SecCoverage)
        .filter(SecCoverage.ticker == coverage.ticker)
        .first()
    )
    if row is None:
        row = SecCoverage(ticker=coverage.ticker)
        db.add(row)

    row.cik = coverage.cik
    row.company_name = coverage.company_name
    row.status = coverage.status.value
    row.note = coverage.note
    row.last_checked_at = datetime.now(timezone.utc)
    return row


def _store_filings(db: Session, coverage: TickerCoverage) -> int:
    stored = 0
    for filing in coverage.filings:
        exists = (
            db.query(SecFiling)
            .filter(
                SecFiling.accession == filing.accession,
                SecFiling.document == filing.document,
            )
            .first()
        )
        if exists is not None:
            continue
        db.add(SecFiling(
            ticker=coverage.ticker,
            cik=filing.cik,
            form=filing.form,
            filed_date=filing.filed,
            period_date=filing.period,
            accession=filing.accession,
            document=filing.document,
            url=filing.url,
        ))
        stored += 1
    return stored


def _store_insider(db: Session, coverage: TickerCoverage) -> int:
    stored = 0
    for tx in coverage.insider_transactions:
        exists = (
            db.query(InsiderTransactionRow)
            .filter(
                InsiderTransactionRow.accession == tx.accession,
                InsiderTransactionRow.insider_name == tx.insider,
                InsiderTransactionRow.transaction_date == tx.transaction_date,
                InsiderTransactionRow.code == tx.code.code,
                InsiderTransactionRow.shares == tx.shares,
            )
            .first()
        )
        if exists is not None:
            continue
        db.add(InsiderTransactionRow(
            ticker=coverage.ticker,
            accession=tx.accession,
            insider_name=tx.insider,
            is_director=tx.is_director,
            is_officer=tx.is_officer,
            officer_title=tx.officer_title,
            is_ten_percent=tx.is_ten_percent_owner,
            transaction_date=tx.transaction_date,
            filed_date=tx.filed,
            code=tx.code.code,
            code_label=tx.code.label_cs,
            signal=tx.code.signal.value,
            shares=tx.shares,
            price_per_share=tx.price_per_share,
            acquired=tx.acquired,
            shares_owned_after=tx.shares_owned_after,
        ))
        stored += 1
    return stored


# ==============================================================================
# Outlook
# ==============================================================================

def analyze_filing(
    db: Session,
    filing: SecFiling,
    *,
    client: SecEdgarClient | None = None,
) -> str | None:
    """
    Read one filing's narrative for guidance and operational facts.

    Returns the stored Czech summary, or None if the filing could not be read.
    Leaves `analysis` NULL in that case — the UI shows "not analysed", which
    is a different statement from "nothing notable in it".
    """
    client = client or SecEdgarClient()

    try:
        html = client._get(filing.url).text
    except SecError as e:
        logger.warning("Nelze stáhnout {}: {}", filing.url, e)
        return None

    text, truncated = extract_text(html)
    if truncated:
        logger.info("{} {} zkráceno na {} znaků",
                    filing.ticker, filing.form, MAX_FILING_CHARS)

    from app.services.llm import LLMError

    try:
        outlook = analyze_outlook(
            text,
            ticker=filing.ticker,
            form=filing.form,
            period=str(filing.period_date or filing.filed_date),
        )
    except LLMError as e:
        logger.warning("Analýza {} {} selhala: {}", filing.ticker, filing.form, e)
        return None

    summary = format_outlook(outlook, truncated=truncated)
    filing.analysis = summary
    filing.analyzed_at = datetime.now(timezone.utc)
    return summary


def format_outlook(outlook: dict, *, truncated: bool = False) -> str:
    """
    Render the model's reading of a filing as Czech text.

    An absent field is printed as absent. "Firma výhled neuvádí" is a real and
    useful finding about a quarter; leaving the line out entirely would let it
    be mistaken for one we did not look for.
    """
    lines: list[str] = []

    guidance = outlook.get("guidance")
    direction = (outlook.get("guidance_direction") or "NONE").upper()
    direction_cs = {
        "RAISED": "zvýšen", "LOWERED": "snížen",
        "MAINTAINED": "potvrzen", "NONE": "neuveden",
    }.get(direction, direction)

    if guidance:
        lines.append(f"**Výhled ({direction_cs}):** {guidance}")
    else:
        lines.append("**Výhled:** firma v této zprávě žádný neuvádí.")

    backlog = outlook.get("orders_backlog")
    if backlog:
        lines.append(f"**Objednávky / backlog:** {backlog}")

    cylinders = outlook.get("cylinders_evidence") or []
    if cylinders:
        lines.append("**Provozní fakta (válce):**")
        lines.extend(f"  - {item}" for item in cylinders)

    risks = outlook.get("risks_new") or []
    if risks:
        lines.append("**Nová/zhoršená rizika:**")
        lines.extend(f"  - {item}" for item in risks)

    summary = outlook.get("summary_cs")
    if summary:
        lines.append(f"\n{summary}")

    if truncated:
        lines.append(
            "\n_Pozn.: dokument byl pro analýzu zkrácen — konec zprávy nebyl "
            "přečten._"
        )

    return "\n".join(lines)


# ==============================================================================
# Orchestration
# ==============================================================================

def sync_ticker(
    db: Session,
    ticker: str,
    *,
    client: SecEdgarClient | None = None,
    with_outlook: bool = True,
    max_filings: int = 2,
) -> SyncResult:
    """
    Refresh one ticker's SEC data.

    Never raises for a ticker SEC does not cover — that comes back as a status.
    """
    client = client or SecEdgarClient()
    coverage = client.fetch_coverage(ticker, max_filings=max_filings)
    _upsert_coverage(db, coverage)

    result = SyncResult(
        ticker=coverage.ticker,
        status=coverage.status.value,
        company_name=coverage.company_name,
        note=coverage.note,
    )

    if coverage.status is not CoverageStatus.COVERED:
        db.commit()
        return result

    result.filings_stored = _store_filings(db, coverage)
    result.insider_stored = _store_insider(db, coverage)

    # Results: exact numbers, straight from XBRL. This is the part that matters.
    try:
        fundamentals: Fundamentals = fetch_fundamentals(
            coverage.ticker, coverage.cik, client=client
        )
        result.findings = fundamentals.findings
        result.gaps = fundamentals.gaps
    except SecError as e:
        result.error = f"Výsledky se nepodařilo načíst: {e}"
        logger.warning("XBRL {} selhalo: {}", coverage.ticker, e)

    db.commit()

    # Outlook: narrative, so it goes through the model. Done after the commit
    # so a failed analysis never costs us the filings we already fetched.
    if with_outlook:
        pending = (
            db.query(SecFiling)
            .filter(
                SecFiling.ticker == coverage.ticker,
                SecFiling.analysis.is_(None),
            )
            .order_by(SecFiling.filed_date.desc())
            .limit(1)
            .all()
        )
        for filing in pending:
            if analyze_filing(db, filing, client=client) is not None:
                db.commit()

    return result


def sync_held_tickers(
    db: Session,
    tickers: list[str],
    *,
    client: SecEdgarClient | None = None,
    with_outlook: bool = True,
) -> list[SyncResult]:
    """
    Refresh every held position.

    One ticker failing does not stop the rest — a portfolio-wide refresh that
    aborts on the first foreign listing would be useless here, where five of
    fourteen holdings are not SEC filers.
    """
    client = client or SecEdgarClient()
    results: list[SyncResult] = []

    for ticker in tickers:
        try:
            results.append(
                sync_ticker(db, ticker, client=client, with_outlook=with_outlook)
            )
        except Exception as e:
            logger.exception("SEC sync {} selhal", ticker)
            db.rollback()
            results.append(SyncResult(
                ticker=ticker.upper(),
                status="ERROR",
                error=str(e),
            ))

    return results

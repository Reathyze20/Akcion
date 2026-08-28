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
    WRAPPER_FORMS,
    CoverageStatus,
    FilingDocument,
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

#: Below this, what we read is a cover page rather than a report. A 6-K cover
#: runs 1,400-2,400 characters of "the following is furnished herewith"; the
#: shortest real quarterly announcement we have seen is an order of magnitude
#: larger. The number only decides whether to *say* the source was thin — the
#: text is analysed either way.
MIN_SUBSTANTIVE_CHARS: Final[int] = 6_000

#: At most this many exhibits are appended to one filing. A 20-F carries a
#: dozen; reading all of them would send a novel to the model for no gain.
MAX_EXHIBITS: Final[int] = 3


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


@dataclass(frozen=True)
class FilingText:
    """The text of a filing, and an honest account of where it came from."""

    text: str
    truncated: bool
    #: Filenames actually read, in the order they were concatenated.
    sources: list[str]
    #: Set when the text is too thin to be a report. Carried into the summary
    #: so "we read a cover page" cannot be mistaken for "the quarter was quiet".
    thin_note: str | None = None


def read_filing(
    client: SecEdgarClient,
    *,
    url: str,
    form: str,
    cik: str,
    accession: str,
) -> FilingText | None:
    """
    Assemble everything worth reading in one filing.

    For a 10-K or 10-Q the filed document *is* the report. For a 6-K or 8-K it
    is a cover page naming an exhibit, and the exhibit is the quarter — so
    those forms get their EX-99 attachments appended. A filing whose primary
    document is unexpectedly thin gets the same treatment regardless of form,
    because the wrapper habit is not confined to the two forms that mandate it.

    Returns None only when the primary document itself cannot be fetched. An
    exhibit that fails is logged and skipped: three quarters of a report beats
    discarding it.
    """
    try:
        primary = extract_text(client._get(url).text)[0]
    except SecError as e:
        logger.warning("Nelze stáhnout {}: {}", url, e)
        return None

    parts = [primary]
    sources = [url.rsplit("/", 1)[-1]]

    needs_exhibits = (
        form.upper() in WRAPPER_FORMS or len(primary) < MIN_SUBSTANTIVE_CHARS
    )
    if needs_exhibits:
        for exhibit in _substantive_exhibits(client, cik=cik, accession=accession):
            if exhibit.filename in sources:
                continue
            try:
                text = extract_text(client._get(exhibit.url).text)[0]
            except SecError as e:
                logger.warning("Přílohu {} nelze přečíst: {}", exhibit.filename, e)
                continue
            label = exhibit.description or exhibit.type
            parts.append(
                f"\n\n=== {exhibit.type} — {label} ===\n{text}"
            )
            sources.append(exhibit.filename)

    combined = "".join(parts)
    truncated = len(combined) > MAX_FILING_CHARS
    if truncated:
        combined = combined[:MAX_FILING_CHARS]

    thin_note = None
    if len(combined) < MIN_SUBSTANTIVE_CHARS:
        thin_note = (
            f"Podání má jen průvodní stranu ({len(combined)} znaků) a žádnou "
            f"věcnou přílohu. Co v souhrnu nenajdeš, v přečteném dokumentu "
            f"nebylo — neznamená to, že se nic nestalo."
        )

    return FilingText(
        text=combined, truncated=truncated, sources=sources, thin_note=thin_note,
    )


def _substantive_exhibits(
    client: SecEdgarClient, *, cik: str, accession: str,
) -> list[FilingDocument]:
    """The EX-99 attachments of one filing, newest sequence first, capped."""
    try:
        documents = client.fetch_documents(cik, accession)
    except SecError as e:
        logger.warning("Seznam příloh {} nelze přečíst: {}", accession, e)
        return []
    return [d for d in documents if d.is_substantive_exhibit][:MAX_EXHIBITS]


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


def _purge_filings(db: Session, ticker: str) -> int:
    """
    Drop everything stored for a ticker we can no longer resolve.

    Called when a refresh concludes the ticker is not an SEC filer after all.
    Keeping the rows would leave another company's numbers presented as this
    holding's.
    """
    filings = db.query(SecFiling).filter(SecFiling.ticker == ticker).delete()
    insider = (
        db.query(InsiderTransactionRow)
        .filter(InsiderTransactionRow.ticker == ticker)
        .delete()
    )
    if filings or insider:
        logger.warning(
            "{}: mazu {} podani a {} insider zaznamu ulozenych pod chybnym parovanim",
            ticker, filings, insider,
        )
    return filings + insider


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

    source = read_filing(
        client,
        url=filing.url,
        form=filing.form,
        cik=filing.cik,
        accession=filing.accession,
    )
    if source is None:
        return None

    if source.truncated:
        logger.info("{} {} zkráceno na {} znaků",
                    filing.ticker, filing.form, MAX_FILING_CHARS)
    if len(source.sources) > 1:
        logger.info("{} {}: čteno {} dokumentů ({})", filing.ticker, filing.form,
                    len(source.sources), ", ".join(source.sources))

    from app.services.llm import LLMError

    try:
        outlook = analyze_outlook(
            source.text,
            ticker=filing.ticker,
            form=filing.form,
            period=str(filing.period_date or filing.filed_date),
        )
    except LLMError as e:
        logger.warning("Analýza {} {} selhala: {}", filing.ticker, filing.form, e)
        return None

    summary = format_outlook(
        outlook, truncated=source.truncated, thin_note=source.thin_note,
    )
    filing.analysis = summary
    filing.analyzed_at = datetime.now(timezone.utc)

    # The same findings, in a form something can query. The markdown above is
    # for reading; these rows are what the cylinder rubric and the portfolio
    # concentration check need, and until now they had no way to see a going
    # concern the model had already found and written into prose.
    record_findings(db, filing, outlook)
    return summary


def record_findings(db, filing, outlook: dict) -> list:
    """
    Store one filing's red flags as rows, replacing whatever it said before.

    Replacing rather than appending: re-analysing a filing is a correction of
    the same document, not a second opinion about it. Findings from OTHER
    filings are untouched — a warning the company later dropped is still a fact
    about the quarter it appeared in.

    A flag with no sentence is skipped. It could not be shown and could not be
    checked, so it is not a finding.
    """
    from app.models.sec_finding import SecFinding

    flags = outlook.get("red_flags") or []

    db.query(SecFinding).filter(SecFinding.accession == filing.accession).delete(
        synchronize_session=False
    )

    rows = []
    seen: set[str] = set()
    for flag in flags:
        if not isinstance(flag, dict):
            continue
        fact = (flag.get("fact_cs") or "").strip()
        if not fact or fact in seen:
            continue
        seen.add(fact)
        row = SecFinding(
            ticker=filing.ticker,
            accession=filing.accession,
            form=filing.form,
            filed_date=filing.filed_date,
            period_date=filing.period_date,
            severity=(flag.get("severity") or "MEDIUM").strip().upper(),
            category=(flag.get("category") or None),
            fact_cs=fact,
            quote=(flag.get("quote") or None),
        )
        db.add(row)
        rows.append(row)

    if rows:
        logger.info("{} {}: {} nálezů uloženo strukturovaně",
                    filing.ticker, filing.form, len(rows))
    return rows


def format_outlook(
    outlook: dict, *, truncated: bool = False, thin_note: str | None = None,
) -> str:
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

    # Red flags come first inside the body — they are the reason to read this.
    flags = outlook.get("red_flags") or []
    if flags:
        order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
        ranked = sorted(flags, key=lambda f: order.get(
            (f.get("severity") or "MEDIUM").upper(), 3))
        marker = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡"}
        lines.insert(0, "**Varovné signály:**")
        for i, flag in enumerate(ranked, start=1):
            sev = (flag.get("severity") or "MEDIUM").upper()
            lines.insert(i, f"  {marker.get(sev, '🟡')} {flag.get('fact_cs', '')}")
        lines.insert(len(ranked) + 1, "")

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

    if thin_note:
        lines.append(f"\n_Pozn.: {thin_note}_")

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

    # A foreign private issuer files 20-F and 6-K rather than 10-K/10-Q, and
    # `fetch_coverage` has already collected them. Returning here on anything
    # that is not COVERED threw those away and left RADCOM — a real holding —
    # with zero stored filings and nothing to analyse.
    if coverage.status is CoverageStatus.FOREIGN_PRIVATE_ISSUER:
        result.filings_stored = _store_filings(db, coverage)
        result.insider_stored = _store_insider(db, coverage)
    elif coverage.status is not CoverageStatus.COVERED:
        # Anything stored under a previous, wrong resolution has to go. DBO.TO
        # was matched to "Invesco DB Oil Fund" by an earlier version that
        # stripped the exchange suffix, and four of that fund's filings ended
        # up attached to a Toronto holding. Fixing the matcher does not unstick
        # rows already written, and a wrong company reads exactly as
        # trustworthy as the right one.
        _purge_filings(db, coverage.ticker)
        db.commit()
        return result

    if coverage.status is CoverageStatus.FOREIGN_PRIVATE_ISSUER:
        # XBRL still carries their numbers even on the foreign form schedule.
        try:
            foreign_data = fetch_fundamentals(
                coverage.ticker, coverage.cik, client=client
            )
            result.findings = foreign_data.findings
            result.gaps = foreign_data.gaps
        except SecError as e:
            result.error = f"Výsledky se nepodařilo načíst: {e}"
        db.commit()
        _analyze_newest(db, coverage.ticker, client, with_outlook)
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

    _analyze_newest(db, coverage.ticker, client, with_outlook)
    return result


def _analyze_newest(
    db: Session,
    ticker: str,
    client: SecEdgarClient,
    with_outlook: bool,
) -> None:
    """
    Read the newest unanalysed filing's narrative.

    Runs after the commit, so a failed analysis never costs us the filings we
    already fetched.
    """
    if not with_outlook:
        return

    newest = (
        db.query(SecFiling)
        .filter(SecFiling.ticker == ticker, SecFiling.analysis.is_(None))
        .order_by(SecFiling.filed_date.desc())
        .first()
    )
    if newest is not None and analyze_filing(db, newest, client=client) is not None:
        db.commit()


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

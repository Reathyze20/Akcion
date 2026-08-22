"""
SEC EDGAR models — filings and insider transactions.

Stores what the regulator says about held positions. The schema's two unusual
choices are both there to stop an absence being read as a finding — see
`migrations/add_sec_filings.sql` for the full reasoning:

* `SecCoverage.status` distinguishes a company that files nothing this quarter
  from one that does not file with the SEC at all.
* `InsiderTransaction.signal` comes from the SEC transaction code, never from
  the acquired/disposed flag. A gift and a tax withholding are both disposals
  and neither is a sale.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from .base import Base


class SecCoverage(Base):
    """Whether — and why — we have SEC data for a ticker."""

    __tablename__ = "sec_coverage"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(20), nullable=False, unique=True, index=True)
    cik = Column(String(10), nullable=True, doc="Ten-digit zero-padded SEC CIK")
    company_name = Column(String(255), nullable=True)
    status = Column(
        # 32, not 20: FOREIGN_PRIVATE_ISSUER is 22 characters and silently
        # failed to store when the column was first sized.
        String(32),
        nullable=False,
        doc=(
            "COVERED | NOT_AN_SEC_FILER | LOOKUP_FAILED. NOT_AN_SEC_FILER is a "
            "fact about the listing venue and says nothing about the company."
        ),
    )
    note = Column(String(500), nullable=True, doc="Czech explanation for the UI")
    last_checked_at = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="NULL = never checked, which is not the same as 'nothing found'",
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SecFiling(Base):
    """One 10-K or 10-Q."""

    __tablename__ = "sec_filings"
    __table_args__ = (
        UniqueConstraint("accession", "document", name="uq_sec_filing_accession"),
        Index("idx_sec_filings_ticker_filed", "ticker", "filed_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(20), nullable=False, index=True)
    cik = Column(String(10), nullable=False)
    form = Column(String(20), nullable=False, doc="10-K, 10-Q, ...")
    filed_date = Column(Date, nullable=False)
    period_date = Column(Date, nullable=True, doc="Period the filing reports on")
    accession = Column(String(25), nullable=False)
    document = Column(String(255), nullable=False)
    url = Column(String(500), nullable=True)
    analysis = Column(
        Text,
        nullable=True,
        doc=(
            "Czech summary of the filing. NULL = not analysed yet — the UI must "
            "show that as such, never as 'nothing notable found'."
        ),
    )
    analyzed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class InsiderTransaction(Base):
    """One line of a Form 4."""

    __tablename__ = "insider_transactions"
    __table_args__ = (
        UniqueConstraint(
            "accession", "insider_name", "transaction_date", "code", "shares",
            name="uq_insider_tx",
        ),
        Index("idx_insider_tx_ticker_date", "ticker", "transaction_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(20), nullable=False, index=True)
    accession = Column(String(25), nullable=False)

    insider_name = Column(String(255), nullable=False)
    is_director = Column(Boolean, default=False)
    is_officer = Column(Boolean, default=False)
    officer_title = Column(String(255), nullable=True)
    is_ten_percent = Column(Boolean, default=False)

    transaction_date = Column(Date, nullable=True)
    filed_date = Column(Date, nullable=True)

    code = Column(String(2), nullable=False, doc="SEC Table I/II transaction code")
    code_label = Column(String(100), nullable=True, doc="What the code means, in Czech")
    signal = Column(
        String(12),
        nullable=False,
        doc=(
            "BUY | SELL | NO_SIGNAL. From the transaction code, never from "
            "acquired/disposed: a gift (G) and a tax withholding (F) are "
            "disposals that reflect no decision to sell."
        ),
    )

    shares = Column(Float, nullable=True)
    price_per_share = Column(
        Float,
        nullable=True,
        doc="NULL for grants and gifts. Zero is a price; the absence of one is not.",
    )
    acquired = Column(Boolean, nullable=True, doc="SEC's A/D flag, kept as reported")
    shares_owned_after = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

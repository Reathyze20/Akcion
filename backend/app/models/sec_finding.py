"""
Material warnings from a filing, in a form something can query.

The problem
-----------
`analyze_outlook` already extracts red flags with a severity and a verbatim
quote — going concern, controls declared not effective, restatements,
concentration, dilution. All of it is then rendered into one Czech markdown
blob in `sec_filings.analysis` and that is where it stays.

Which means the cylinder rubric, which most needs those findings, cannot read
them. SMSI and ECOR both carry going-concern warnings and both were assessed
without either one, because reading a severity back out of prose is exactly
what this codebase refuses to do.

Now or never, again
-------------------
Re-reading past filings to structure them would spend API credit on work the
Claude subscription already covers, so the past stays in markdown. What is not
optional is that every filing analysed FROM TODAY writes its findings here as
well. A quarter from now the portfolio has structured findings for whatever it
has read since; a quarter from now without this table it has none, and there is
no way to catch up except by paying to read everything twice.

Severity is the model's, the quote is the filing's
--------------------------------------------------
Both are kept because neither is sufficient. A severity with no quote cannot be
checked, and an unverifiable warning about real money is worse than none. A
quote with no severity leaves every finding competing equally for attention on
a screen that has room for three.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from .base import Base

#: The model's own vocabulary, ordered. CRITICAL means the filing questions
#: whether the company continues; HIGH means the thesis is materially changed.
SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"

SEVERITY_ORDER = {SEVERITY_CRITICAL: 0, SEVERITY_HIGH: 1, SEVERITY_MEDIUM: 2}


class SecFinding(Base):
    """One material warning a filing made about itself."""

    __tablename__ = "sec_findings"

    id = Column(Integer, primary_key=True)

    ticker = Column(String(20), nullable=False, index=True)
    #: Which filing said it. Findings are superseded by a newer filing rather
    #: than edited: a warning the company later dropped is still a fact about
    #: the quarter it appeared in.
    accession = Column(String(25), nullable=False)
    form = Column(String(20), nullable=True)
    filed_date = Column(Date, nullable=True)
    period_date = Column(Date, nullable=True)

    severity = Column(String(12), nullable=False, doc="CRITICAL | HIGH | MEDIUM")
    category = Column(
        String(60), nullable=True, doc="going_concern, dilution, controls, ..."
    )
    fact_cs = Column(Text, nullable=False, doc="One Czech sentence, with dates and numbers")
    #: Verbatim from the filing. Without it the finding cannot be checked, and
    #: an unverifiable warning about real money is worse than none.
    quote = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())

    __table_args__ = (
        # One finding per filing per sentence. Re-analysing a filing must
        # refresh rather than duplicate.
        UniqueConstraint("accession", "fact_cs", name="uq_finding_per_filing"),
        Index("idx_findings_ticker_severity", "ticker", "severity"),
    )

    @property
    def is_material(self) -> bool:
        """Whether this changes the thesis rather than colouring it."""
        return self.severity in (SEVERITY_CRITICAL, SEVERITY_HIGH)

    def __repr__(self) -> str:
        return f"<SecFinding {self.ticker} {self.severity} {self.category}>"

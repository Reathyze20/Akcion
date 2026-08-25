"""
Cache for `gomes_fit.fit_candidate()`, read by find_dossier's FIT layer.

`fit_candidate()` needs a live bar fetch and the market gauge — real network,
paid in the sense that `find_dossier.build()` promises never to make one (see
its own docstring: "Nesahá na síť"). So the fetch happens once, in `enrich()`,
same as Yahoo/SEC/Finnhub above it, and `build()` only ever reads what is
already here.
"""

from __future__ import annotations

from sqlalchemy import Column, Date, String, TIMESTAMP, Text
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base


class GomesFitCache(Base):
    """One ticker's most recent `Fit`, flattened for storage."""

    __tablename__ = "gomes_fit_cache"

    ticker = Column(String(20), primary_key=True)
    as_of = Column(Date, nullable=False)
    computed_at = Column(TIMESTAMP(timezone=True), nullable=False)
    summary_cs = Column(Text, nullable=False)
    #: list of {name, label_cs, value, bucket, below, of} — one per computable
    #: profile feature. Bucket is TYPICKE | NA_OKRAJI | MIMO.
    fits_json = Column(JSONB, nullable=False)
    #: Feature names `fit_candidate` could not compute for this ticker.
    uncomputable_json = Column(JSONB, nullable=False)

    def __repr__(self) -> str:
        return f"<GomesFitCache {self.ticker} as_of={self.as_of}>"

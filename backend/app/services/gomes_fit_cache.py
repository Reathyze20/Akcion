"""
Write `gomes_fit_cache`, the cache `find_dossier`'s FIT layer reads.

A separate module from `find_dossier.py` on purpose: that file has a textual
guarantee (`test_find_dossier.py::TestNothingThatFeedsTheGateIsWritten`) that
it never calls `db.add`/`db.commit` itself, the same way `cylinder_intake`
and `lifecycle_intake` are the only door onto the tables they write. This
table feeds no gate — it is a display cache — but the writing still belongs
here, not inline in the dossier builder.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.gomes_fit_cache import GomesFitCache
from app.services.entry_features import FEATURE_LABELS_CS
from app.services.gomes_fit import Fit, fit_candidate


def refresh(db: Session, ticker: str) -> Fit:
    """
    Compute `fit_candidate()` for one ticker and cache the result.

    Raises whatever `fit_candidate()` raises (network error, not enough
    history) — the caller decides how to degrade; this function only writes
    on success. Commits its own transaction, same as `sync_ticker`: this is
    cache-only, not a write a caller's failure elsewhere should roll back.
    """
    fit = fit_candidate(ticker)

    row = db.query(GomesFitCache).filter(GomesFitCache.ticker == ticker).first()
    if row is None:
        row = GomesFitCache(ticker=ticker)
        db.add(row)

    row.as_of = fit.as_of
    row.computed_at = datetime.now(timezone.utc)
    row.summary_cs = fit.summary_cs
    row.fits_json = [
        {
            "name": f.name, "label_cs": f.label_cs, "value": f.value,
            "bucket": f.bucket, "below": f.below, "of": f.of,
        }
        for f in fit.fits
    ]
    row.uncomputable_json = [FEATURE_LABELS_CS.get(n, n) for n in fit.uncomputable]

    db.commit()
    return fit

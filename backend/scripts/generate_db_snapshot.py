"""
Generuje čerstvý read-only snapshot databáze pro analytické workflow.
"""

from __future__ import annotations

import json
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

from app.database.connection import initialize_database, get_session
from app.config.settings import get_settings
import app.models
import app.models.trading
import app.models.analysis
from app.models.portfolio import Position
from app.models.stock import Stock
from app.models.gomes import StockLifecycleModel
from app.core.tickers import canonical_ticker, variants_of

settings = get_settings()
initialize_database(settings.database_url)
db = get_session()

positions = db.query(Position).filter(Position.shares_count > 0).all()
stocks = db.query(Stock).all()
lifecycles = db.query(StockLifecycleModel).all()

snapshot = {
    "generated_at": "2026-08-24T17:30:00Z",
    "holdings_count": len(positions),
    "holdings": [
        {
            "ticker": p.ticker,
            "canonical_ticker": canonical_ticker(p.ticker),
            "shares_count": float(p.shares_count),
            "avg_cost": float(p.avg_cost) if p.avg_cost is not None else None,
            "currency": p.currency,
        }
        for p in positions
    ],
    "stocks_count": len(stocks),
    "stocks": [
        {
            "id": s.id,
            "ticker": s.ticker,
            "canonical_ticker": canonical_ticker(s.ticker),
            "company_name": s.company_name,
            "source_key": s.source_key,
            "speaker": s.speaker,
            "green_line": float(s.green_line) if s.green_line is not None else None,
            "red_line": float(s.red_line) if s.red_line is not None else None,
            "grey_line": float(s.grey_line) if s.grey_line is not None else None,
            "conviction_score": s.conviction_score,
            "price_zone": s.price_zone,
            "sentiment": s.sentiment,
        }
        for s in stocks
    ],
    "lifecycles_count": len(lifecycles),
    "lifecycles": [
        {
            "ticker": l.ticker,
            "phase": l.phase,
            "phase_reached": getattr(l, "phase_reached", None),
            "rough_patch_since": str(getattr(l, "rough_patch_since", None)),
        }
        for l in lifecycles
    ]
}

out_path = Path("C:/tmp/akcion/db_snapshot.json")
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Snapshot successfully written to {out_path} ({len(positions)} positions, {len(stocks)} stocks, {len(lifecycles)} lifecycles).")
db.close()

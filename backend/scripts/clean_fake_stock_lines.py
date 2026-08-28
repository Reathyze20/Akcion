"""
Vyčistí vymyšlené a testovací cenové linie ze starého AI stubu.

Pravidlo: Pouze záznamy s source_key='GOMES' smějí nést autoritativní
Gomesovy cenové linie (green_line, red_line, grey_line). Záznamy s
source_key='OTHER' (jako KUYA.V 1.2/2.0, MSTY, TSLY, NVDY) nesmí nést
podvržené linie.
"""

from __future__ import annotations

import logging
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

from app.database.connection import initialize_database, get_session
from app.config.settings import get_settings
import app.models
import app.models.trading
import app.models.analysis
from app.models.stock import Stock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def clean_fake_lines():
    settings = get_settings()
    initialize_database(settings.database_url)
    db = get_session()
    if db is None:
        raise RuntimeError("Database session could not be created")

    try:
        # 1. Odstranit/vyčistit fiktivní testovací tickery (NVDY, MSTY, TSLY, XMMO.V)
        test_tickers = ["NVDY", "MSTY", "TSLY", "XMMO.V"]
        test_rows = db.query(Stock).filter(Stock.ticker.in_(test_tickers)).all()
        for row in test_rows:
            logger.info(f"Deleting test stock fixture: {row.ticker} (source={row.source_key})")
            db.delete(row)

        # 2. Resetovat podvržené linie u reálných tickerů se source_key='OTHER' (např. KUYA.V)
        other_stocks_with_lines = (
            db.query(Stock)
            .filter(Stock.source_key != "GOMES")
            .filter((Stock.green_line.isnot(None)) | (Stock.red_line.isnot(None)))
            .all()
        )
        for row in other_stocks_with_lines:
            logger.info(
                f"Resetting fabricated lines for {row.ticker} (source={row.source_key}): "
                f"green={row.green_line} -> None, red={row.red_line} -> None"
            )
            row.green_line = None
            row.red_line = None
            row.grey_line = None

        db.commit()
        logger.info("Cleanup completed successfully.")
    except Exception as e:
        db.rollback()
        logger.error(f"Cleanup failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    clean_fake_lines()

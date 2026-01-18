"""
Background Alert Scheduler
============================

Periodically checks for high-confidence opportunities and sends alerts.

Usage:
    python -m app.services.alert_scheduler
    
Or run as background service with systemd/Windows Task Scheduler.

Author: GitHub Copilot with Claude Sonnet 4.5
Date: 2025-01-17
Version: 1.0.0
"""

import asyncio
import logging
import os
from datetime import datetime, time

from app.database.connection import get_db_session
from app.services.notifications import check_and_send_alerts


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ==============================================================================
# Configuration
# ==============================================================================

CHECK_INTERVAL_MINUTES = int(os.getenv('ALERT_CHECK_INTERVAL', '30'))  # Default: 30 min
MIN_CONFIDENCE = float(os.getenv('ALERT_MIN_CONFIDENCE', '80'))  # Default: 80%
MARKET_OPEN_HOUR = 9  # 9:00 AM
MARKET_CLOSE_HOUR = 16  # 4:00 PM


# ==============================================================================
# Scheduler
# ==============================================================================

def is_market_hours() -> bool:
    """Check if current time is during market hours (9 AM - 4 PM)"""
    now = datetime.now().time()
    market_open = time(MARKET_OPEN_HOUR, 0)
    market_close = time(MARKET_CLOSE_HOUR, 0)
    return market_open <= now <= market_close


async def run_alert_check():
    """Single alert check iteration"""
    try:
        logger.info("Running alert check...")
        
        # Get database session
        with get_db_session() as db:
            alerts = await check_and_send_alerts(
                db=db,
                min_confidence=MIN_CONFIDENCE,
            )
            
            if alerts:
                logger.info(f"✅ Sent {len(alerts)} alerts")
            else:
                logger.info("No alerts triggered")
                
    except Exception as e:
        logger.error(f"Alert check failed: {e}", exc_info=True)


async def scheduler_loop():
    """Main scheduler loop"""
    logger.info(f"🚀 Alert scheduler started")
    logger.info(f"Check interval: {CHECK_INTERVAL_MINUTES} minutes")
    logger.info(f"Min confidence: {MIN_CONFIDENCE}%")
    logger.info(f"Market hours: {MARKET_OPEN_HOUR}:00 - {MARKET_CLOSE_HOUR}:00")
    
    while True:
        try:
            # Only run during market hours
            if is_market_hours():
                await run_alert_check()
            else:
                logger.debug("Outside market hours, skipping check")
            
            # Wait for next interval
            await asyncio.sleep(CHECK_INTERVAL_MINUTES * 60)
            
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
            break
        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)
            await asyncio.sleep(60)  # Wait 1 minute before retrying


# ==============================================================================
# Entry Point
# ==============================================================================

if __name__ == "__main__":
    asyncio.run(scheduler_loop())

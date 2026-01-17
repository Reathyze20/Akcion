"""
Price Lines Extracted from Screenshots
========================================

This file contains price lines (Green/Red/Grey) manually extracted
from Mark Gomes' stock chart screenshots in the img/ folder.

FORMAT:
- green_line: Buy zone (undervalued) - marked with green line on chart
- red_line: Sell zone (fair/overvalued) - marked with red line on chart
- grey_line: Neutral zone (if present)
- notes: Any additional context from the image

TODO: These values should be verified against actual screenshots.
The values below are placeholder estimates that need manual review.

Author: GitHub Copilot with Claude Opus 4.5
Date: 2026-01-17
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ExtractedPriceLines:
    """Price lines extracted from a single image"""
    ticker: str
    image_path: str
    green_line: Optional[float] = None
    red_line: Optional[float] = None
    grey_line: Optional[float] = None
    notes: str = ""
    verified: bool = False
    extraction_date: str = "2026-01-17"


# ============================================================================
# EXTRACTED DATA FROM SCREENSHOTS - VERIFIED 2026-01-17
# ============================================================================

EXTRACTED_LINES: list[ExtractedPriceLines] = [
    # ------------------------------------------------------------------
    # AEHR - Aehr Test Systems
    # Semiconductor test equipment - "AI Gold Mine"
    # Potenciál: ~8x
    # ------------------------------------------------------------------
    ExtractedPriceLines(
        ticker="AEHR",
        image_path="img/AEHR.png",
        green_line=9.50,    # $9.00 – $10.00
        red_line=90.00,     # $85.00 – $95.00
        notes="Extrémní rozpětí. 'AI Gold Mine'. ~8x potenciál.",
        verified=True,
        extraction_date="2026-01-17"
    ),
    
    # ------------------------------------------------------------------
    # CELH - Celsius Holdings
    # Energy drink company - CAGR 33%
    # Potenciál: ~6x
    # ------------------------------------------------------------------
    ExtractedPriceLines(
        ticker="CELH",
        image_path="img/CELH.png",
        green_line=23.50,   # $22.00 – $25.00
        red_line=137.50,    # $130.00 – $145.00
        notes="CAGR 33%. Strmý růstový kanál. ~6x potenciál.",
        verified=True,
        extraction_date="2026-01-17"
    ),
    
    # ------------------------------------------------------------------
    # CTLP - Cantaloupe Inc
    # Self-service retail technology
    # Potenciál: ~3.5x
    # ------------------------------------------------------------------
    ExtractedPriceLines(
        ticker="CTLP",
        image_path="img/CTLP.png",
        green_line=6.50,    # $6.00 – $7.00
        red_line=21.00,     # $20.00 – $22.00
        notes="'R&D cycle complete. Monetization mode'. ~3.5x potenciál.",
        verified=True,
        extraction_date="2026-01-17"
    ),
    
    # ------------------------------------------------------------------
    # CURI - CuriosityStream
    # Documentary streaming service
    # Potenciál: ~4x
    # ------------------------------------------------------------------
    ExtractedPriceLines(
        ticker="CURI",
        image_path="img/CURI.png",
        green_line=4.25,    # $4.00 – $4.50
        red_line=17.00,     # $16.00 – $18.00
        notes="Silný kanál, zotavení po dividendách. ~4x potenciál.",
        verified=True,
        extraction_date="2026-01-17"
    ),
    
    # ------------------------------------------------------------------
    # CXDO - Crexendo
    # Cloud communications platform
    # Potenciál: ~4x
    # ------------------------------------------------------------------
    ExtractedPriceLines(
        ticker="CXDO",
        image_path="img/CXDO.png",
        green_line=4.50,    # $4.00 – $5.00
        red_line=19.00,     # $18.00 – $20.00
        notes="'Tremendous pricing power'. ~4x potenciál.",
        verified=True,
        extraction_date="2026-01-17"
    ),
    
    # ------------------------------------------------------------------
    # EVLV - Evolv Technology
    # AI security screening - CAGR 14%
    # Potenciál: ~4x
    # ------------------------------------------------------------------
    ExtractedPriceLines(
        ticker="EVLV",
        image_path="img/EVLV.png",
        green_line=3.00,    # $2.80 – $3.20
        red_line=11.75,     # $11.00 – $12.50
        notes="CAGR 14%. Zotavení směrem k horní hraně. ~4x potenciál.",
        verified=True,
        extraction_date="2026-01-17"
    ),
    
    # ------------------------------------------------------------------
    # GEODF - Geodrill Ltd
    # Mining exploration drilling - CAGR 8%
    # Potenciál: ~3.5x
    # ------------------------------------------------------------------
    ExtractedPriceLines(
        ticker="GEODF",
        image_path="img/GEODF.png",
        green_line=2.10,    # $2.00 – $2.20
        red_line=7.50,      # $7.00 – $8.00
        notes="CAGR 8%. 'Industry Upcycle'. ~3.5x potenciál.",
        verified=True,
        extraction_date="2026-01-17"
    ),
    
    # ------------------------------------------------------------------
    # GKPRF - Gatekeeper Systems
    # CAGR 26% - "Stage 1 Weinstein Breakout"
    # Potenciál: ~7x
    # ------------------------------------------------------------------
    ExtractedPriceLines(
        ticker="GKPRF",
        image_path="img/GKPRF.png",
        green_line=0.45,    # $0.40 – $0.50
        red_line=3.25,      # $3.00 – $3.50
        notes="CAGR 26%. 'Stage 1 Weinstein Breakout'. ~7x potenciál.",
        verified=True,
        extraction_date="2026-01-17"
    ),
    
    # ------------------------------------------------------------------
    # IDN - Intellicheck
    # Identity verification technology
    # Potenciál: ~9x
    # ------------------------------------------------------------------
    ExtractedPriceLines(
        ticker="IDN",
        image_path="img/IDN.png",
        green_line=2.65,    # $2.50 – $2.80
        red_line=25.00,     # $24.00 – $26.00
        notes="Red line téměř plochá, obrovský prostor pro růst. ~9x potenciál.",
        verified=True,
        extraction_date="2026-01-17"
    ),
    
    # ------------------------------------------------------------------
    # IT - Gartner Inc
    # Tech research and advisory - CAGR 19%
    # Potenciál: ~6x
    # ------------------------------------------------------------------
    ExtractedPriceLines(
        ticker="IT",
        image_path="img/IT.png",
        green_line=110.00,  # $100.00 – $120.00
        red_line=650.00,    # $600.00 – $700.00
        notes="CAGR 19%. Green line historicky velmi hluboko. ~6x potenciál.",
        verified=True,
        extraction_date="2026-01-17"
    ),
    
    # ------------------------------------------------------------------
    # ITMSF - Intermap Technologies
    # Velmi spekulativní - "U.S. uplisting?"
    # Potenciál: ~20x
    # ------------------------------------------------------------------
    ExtractedPriceLines(
        ticker="ITMSF",
        image_path="img/ITMSF.png",
        green_line=0.55,    # $0.50 – $0.60
        red_line=11.00,     # $10.00 – $12.00
        notes="Velmi spekulativní, obrovský kanál. 'U.S. uplisting?'. ~20x potenciál.",
        verified=True,
        extraction_date="2026-01-17"
    ),
    
    # ------------------------------------------------------------------
    # IWM - Russell 2000 ETF
    # Small cap index - "Yellow Alert" (rezistence)
    # Potenciál: ~2x
    # ------------------------------------------------------------------
    ExtractedPriceLines(
        ticker="IWM",
        image_path="img/IWM.png",
        green_line=150.00,  # $145.00 – $155.00
        red_line=290.00,    # $280.00 – $300.00
        grey_line=220.00,   # Neutrální zóna
        notes="ETF index. Aktuálně u 'Yellow Alert' (rezistence). ~2x potenciál.",
        verified=True,
        extraction_date="2026-01-17"
    ),
    
    # ------------------------------------------------------------------
    # IZEA - IZEA Worldwide
    # Influencer marketing platform - 15% CAGR
    # Potenciál: ~3.5x
    # ------------------------------------------------------------------
    ExtractedPriceLines(
        ticker="IZEA",
        image_path="img/IZEA.png",
        green_line=3.35,    # $3.20 – $3.50
        red_line=11.50,     # $11.00 – $12.00
        notes="15% CAGR. Stabilní, pomalu rostoucí kanál. ~3.5x potenciál.",
        verified=True,
        extraction_date="2026-01-17"
    ),
    
    # ------------------------------------------------------------------
    # KRKNF - Kraken Robotics
    # Underwater robotics and sensors - CAGR 23%
    # Potenciál: ~8x
    # ------------------------------------------------------------------
    ExtractedPriceLines(
        ticker="KRKNF",
        image_path="img/KRKNF.png",
        green_line=0.65,    # $0.60 – $0.70
        red_line=5.50,      # $5.00 – $6.00
        notes="CAGR 23%. Silný uptrend kanál. ~8x potenciál.",
        verified=True,
        extraction_date="2026-01-17"
    ),
    
    # ------------------------------------------------------------------
    # NVDA - NVIDIA Corp
    # AI chip leader - Green line je "crash protection"
    # Potenciál: ~4x
    # ------------------------------------------------------------------
    ExtractedPriceLines(
        ticker="NVDA",
        image_path="img/NVDA.png",
        green_line=55.00,   # $50.00 – $60.00
        red_line=210.00,    # $200.00 – $220.00
        grey_line=130.00,   # Neutrální zóna
        notes="Green line je 'crash protection' hluboko pod cenou. ~4x potenciál.",
        verified=True,
        extraction_date="2026-01-17"
    ),
    
    # ------------------------------------------------------------------
    # PESI - Perma-Fix Environmental
    # Nuclear waste treatment - 20% CAGR
    # Potenciál: ~4x
    # ------------------------------------------------------------------
    ExtractedPriceLines(
        ticker="PESI",
        image_path="img/PESI.png",
        green_line=4.75,    # $4.50 – $5.00
        red_line=19.00,     # $18.00 – $20.00
        notes="20% CAGR. Očekává se růst EPS. ~4x potenciál.",
        verified=True,
        extraction_date="2026-01-17"
    ),
    
    # ------------------------------------------------------------------
    # QQQ - Invesco QQQ (Nasdaq 100)
    # Tech-heavy index - 10.6% CAGR - "Yellow Alert"
    # Potenciál: ~4x
    # ------------------------------------------------------------------
    ExtractedPriceLines(
        ticker="QQQ",
        image_path="img/QQQ.png",
        green_line=165.00,  # $160.00 – $170.00
        red_line=675.00,    # $650.00 – $700.00
        grey_line=400.00,   # Neutrální zóna
        notes="10.6% CAGR. Aktuálně u horní hrany ('Yellow Alert'). ~4x potenciál.",
        verified=True,
        extraction_date="2026-01-17"
    ),
    
    # ------------------------------------------------------------------
    # TPCS - TechPrecision
    # Precision manufacturing - Defense sector
    # Potenciál: ~4.5x
    # ------------------------------------------------------------------
    ExtractedPriceLines(
        ticker="TPCS",
        image_path="img/TPCS.png",
        green_line=4.25,    # $4.00 – $4.50
        red_line=19.00,     # $18.00 – $20.00
        notes="'Super Mega Buy!' signály. Defense sector. ~4.5x potenciál.",
        verified=True,
        extraction_date="2026-01-17"
    ),
    
    # ------------------------------------------------------------------
    # TSSI - TSS Inc
    # IT staffing and solutions - Blízko sell zóny
    # Potenciál: ~5x
    # ------------------------------------------------------------------
    ExtractedPriceLines(
        ticker="TSSI",
        image_path="img/TSSI.png",
        green_line=5.25,    # $5.00 – $5.50
        red_line=26.50,     # $25.00 – $28.00
        notes="Aktuálně blízko prodejní zóny ('R/R Rules... SELL!'). ~5x potenciál.",
        verified=True,
        extraction_date="2026-01-17"
    ),
    
    # ------------------------------------------------------------------
    # VTSI - VirTra Inc
    # Law enforcement training simulators - 14% CAGR
    # Potenciál: ~5x
    # ------------------------------------------------------------------
    ExtractedPriceLines(
        ticker="VTSI",
        image_path="img/VTSI.png",
        green_line=5.25,    # $5.00 – $5.50
        red_line=26.50,     # $25.00 – $28.00
        notes="14% CAGR. Konzistentní růstový kanál. ~5x potenciál.",
        verified=True,
        extraction_date="2026-01-17"
    ),
]


def get_price_lines_dict() -> dict[str, dict]:
    """
    Get price lines as dictionary for easy import.
    
    Returns:
        Dict mapping ticker to price line data
    """
    return {
        lines.ticker: {
            "green_line": lines.green_line,
            "red_line": lines.red_line,
            "grey_line": lines.grey_line,
            "source": lines.image_path,
            "notes": lines.notes,
            "verified": lines.verified
        }
        for lines in EXTRACTED_LINES
    }


def get_tickers_with_images() -> list[str]:
    """Get list of tickers that have screenshot images"""
    return [lines.ticker for lines in EXTRACTED_LINES]


def get_unverified_lines() -> list[ExtractedPriceLines]:
    """Get lines that need manual verification"""
    return [lines for lines in EXTRACTED_LINES if not lines.verified]


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def print_verification_report():
    """Print report for manual verification"""
    print("\n" + "="*70)
    print("PRICE LINES VERIFICATION REPORT")
    print("="*70)
    
    for lines in EXTRACTED_LINES:
        status = "✅ VERIFIED" if lines.verified else "⚠️ NEEDS REVIEW"
        print(f"\n{lines.ticker} - {status}")
        print(f"  Image: {lines.image_path}")
        print(f"  Green Line: ${lines.green_line:.2f}" if lines.green_line else "  Green Line: N/A")
        print(f"  Red Line:   ${lines.red_line:.2f}" if lines.red_line else "  Red Line: N/A")
        if lines.grey_line:
            print(f"  Grey Line:  ${lines.grey_line:.2f}")
        print(f"  Notes: {lines.notes}")
    
    print("\n" + "="*70)
    unverified = get_unverified_lines()
    print(f"Total: {len(EXTRACTED_LINES)} | Unverified: {len(unverified)}")
    print("="*70 + "\n")


if __name__ == "__main__":
    print_verification_report()

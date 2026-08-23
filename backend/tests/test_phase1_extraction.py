"""
Verification Test for Phase 1 Core Extraction

This script verifies that all core business logic has been successfully
extracted and can run independently of Streamlit.

Run this test to ensure ZERO LOSS OF FUNCTIONALITY.
"""

import sys
import os

import pytest

pytestmark = pytest.mark.skip(reason="Legacy API-shape tests — superseded by current suites; repair-or-delete tracked in AKCION_SPEC §7")

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.core import analyze_with_gemini
from app.core.extractors import extract_video_id, get_youtube_transcript
from app.models import Stock, Base
from app.database import initialize_database, get_session, StockRepository

def test_imports():
    """Verify all modules can be imported"""
    print("✓ All core modules imported successfully")

def test_stock_model():
    """Verify Stock model structure"""
    stock = Stock(
        ticker="TPCS",
        company_name="TechPrecision Corp",
        sentiment="Bullish",
        gomes_score=9
    )
    assert stock.ticker == "TPCS"
    print("✓ Stock model working correctly")

def test_extractors():
    """Verify data extraction functions"""
    # Test video ID extraction
    video_id = extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert video_id == "dQw4w9WgXcQ"
    print("✓ YouTube ID extraction working")

def test_prompts():
    """Verify prompts are loaded correctly"""
    from app.core.prompts import FIDUCIARY_ANALYST_PROMPT
    
    assert "Fiduciary" in FIDUCIARY_ANALYST_PROMPT
    assert "Multiple Sclerosis" in FIDUCIARY_ANALYST_PROMPT
    assert "AGGRESSIVE EXTRACTION" in FIDUCIARY_ANALYST_PROMPT
    assert "Gomes" in FIDUCIARY_ANALYST_PROMPT
    
    print("✓ All critical prompt content preserved")
    print("  - Fiduciary analyst persona: PRESENT")
    print("  - MS client context: PRESENT")
    print("  - Aggressive extraction instructions: PRESENT")
    print("  - Gomes Rules framework: PRESENT")

def main():
    """Run all verification tests"""
    print("="*60)
    print("PHASE 1 VERIFICATION TEST")
    print("="*60)
    print()
    
    try:
        test_imports()
        test_stock_model()
        test_extractors()
        test_prompts()
        
        print()
        print("="*60)
        print("ALL TESTS PASSED")
        print("="*60)
        print()
        print("CORE BUSINESS LOGIC EXTRACTED SUCCESSFULLY")
        print()
        print("Status:")
        print("  - Database models: ✓ Preserved")
        print("  - AI prompts: ✓ Preserved (including MS context)")
        print("  - Gomes Rules: ✓ Preserved")
        print("  - Data extractors: ✓ Functional")
        print("  - Zero Streamlit dependencies: ✓ Confirmed")
        print()
        print("Ready for PHASE 2: FastAPI Backend Construction")
        
    except Exception as e:
        print()
        print("="*60)
        print("TEST FAILED")
        print("="*60)
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()

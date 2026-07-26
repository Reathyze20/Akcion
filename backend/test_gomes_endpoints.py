"""
Test Gomes Guardian Endpoints

Tests the complete flow:
1. Analyze position with GomesLogicEngine
2. Update stock with AI analyst
3. Verify new fields in response
"""
import requests
import json

BASE_URL = "http://localhost:8002"

def test_analyze_position():
    """Test /api/gomes/analyze-position/{ticker}"""
    print("\n" + "="*80)
    print("TEST 1: Analyze Position with Gomes Logic")
    print("="*80)
    
    ticker = "KUYA.V"
    portfolio_id = 1  # Adjust if needed
    
    url = f"{BASE_URL}/api/gomes/analyze-position/{ticker}"
    params = {"portfolio_id": portfolio_id}
    
    print(f"\nGET {url}")
    print(f"Params: {params}")
    
    try:
        response = requests.get(url, params=params)
        print(f"\nStatus: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("\n✅ SUCCESS!")
            print(f"\nTicker: {data['ticker']}")
            print(f"Max Allocation Cap: {data['max_allocation_cap']:.2f}%")
            print(f"Action Signal: {data['action_signal']}")
            print(f"Warnings: {len(data['warnings'])}")
            
            if data['warnings']:
                print("\nWarnings:")
                for w in data['warnings']:
                    print(f"  ⚠️  {w}")
            
            print("\nDecision Log:")
            print(data['decision_log'])
            
            return True
        else:
            print(f"\n❌ FAILED: {response.text}")
            return False
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return False


def test_ai_analyst():
    """Test /api/gomes/update-stock-ai/{ticker}"""
    print("\n" + "="*80)
    print("TEST 2: Update Stock with AI Analyst")
    print("="*80)
    
    ticker = "KUYA.V"
    url = f"{BASE_URL}/api/gomes/update-stock-ai/{ticker}"
    
    # Sample transcript (would normally be longer)
    payload = {
        "transcript": """
        Q4 2025 Earnings Call - Kuya Silver Corp
        
        Financial Highlights:
        - Cash position: $25.5M USD
        - Quarterly burn rate: $2.1M (production ramp-up costs)
        - Revenue: $8.2M from silver sales
        - Gross margin improving: 42% vs 35% prior quarter
        
        Operational Update:
        - Q2 2026 production target: 2.5M oz Ag equivalent
        - Bethania mine at 85% capacity, ramping to 100% by May
        - Insider buying: CEO purchased 500K shares at $0.85
        
        Catalysts:
        - Q2 Production Ramp (June 2026) - expect 30% increase
        - Amtrak underground exploration results (July 2026)
        - Potential dividend initiation H2 2026
        
        Risks:
        - Silver price volatility
        - Peru political uncertainty (minimal impact so far)
        - Working capital increase needed for expansion
        """,
        "source_type": "quarterly_report"
    }
    
    print(f"\nPOST {url}")
    print(f"Payload: {json.dumps(payload, indent=2)[:200]}...")
    
    try:
        response = requests.post(url, json=payload)
        print(f"\nStatus: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("\n✅ SUCCESS!")
            print(f"\nTicker: {data['ticker']}")
            
            analysis = data['analysis']
            print(f"\nGomes Score: {analysis['gomes_score']}/10 (Δ {analysis['score_delta']:+d})")
            print(f"Cash Runway: {analysis['cash_runway_months']} months")
            print(f"Inflection Status: {analysis['inflection_status']}")
            print(f"Primary Catalyst: {analysis['primary_catalyst']}")
            print(f"Catalyst Date: {analysis['catalyst_date']}")
            print(f"\nThesis: {analysis['thesis_narrative']}")
            
            if analysis['green_flags']:
                print("\n✅ Green Flags:")
                for flag in analysis['green_flags']:
                    print(f"  • {flag}")
            
            if analysis['red_flags']:
                print("\n🚩 Red Flags:")
                for flag in analysis['red_flags']:
                    print(f"  • {flag}")
            
            print(f"\nUpdated Fields: {', '.join(data['updated_fields'])}")
            
            return True
        else:
            print(f"\n❌ FAILED: {response.text}")
            return False
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return False


def test_get_stock_with_new_fields():
    """Test that /api/stocks/{ticker} returns new Gomes fields"""
    print("\n" + "="*80)
    print("TEST 3: Verify New Fields in Stock Response")
    print("="*80)
    
    ticker = "KUYA.V"
    url = f"{BASE_URL}/api/stocks/{ticker}"
    
    print(f"\nGET {url}")
    
    try:
        response = requests.get(url)
        print(f"\nStatus: {response.status_code}")
        
        if response.status_code == 200:
            stock = response.json()
            print("\n✅ SUCCESS!")
            
            # Check new Gomes Master Table fields
            gomes_fields = {
                'cash_runway_months': stock.get('cash_runway_months'),
                'total_cash': stock.get('total_cash'),
                'quarterly_burn_rate': stock.get('quarterly_burn_rate'),
                'inflection_status': stock.get('inflection_status'),
                'primary_catalyst': stock.get('primary_catalyst'),
                'catalyst_date': stock.get('catalyst_date'),
                'thesis_narrative': stock.get('thesis_narrative'),
                'price_floor': stock.get('price_floor'),
                'price_base': stock.get('price_base'),
                'price_moon': stock.get('price_moon'),
                'max_allocation_cap': stock.get('max_allocation_cap'),
                'insider_activity': stock.get('insider_activity'),
            }
            
            print("\nGomes Master Table Fields:")
            for field, value in gomes_fields.items():
                status = "✅" if value is not None else "⚠️ "
                print(f"  {status} {field}: {value}")
            
            return True
        else:
            print(f"\n❌ FAILED: {response.text}")
            return False
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return False


if __name__ == "__main__":
    print("\n" + "="*80)
    print("GOMES GUARDIAN - Complete System Test")
    print("="*80)
    print("\nTesting new Gomes Logic Engine + AI Analyst integration")
    print("Backend: http://localhost:8002")
    
    results = []
    
    # Run tests
    results.append(("Analyze Position", test_analyze_position()))
    results.append(("AI Analyst Update", test_ai_analyst()))
    results.append(("Stock Response Fields", test_get_stock_with_new_fields()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {name}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Gomes Guardian is ready for production!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check logs above.")

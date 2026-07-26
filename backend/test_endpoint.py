"""Test analyze-ticker endpoint directly"""
import requests
import json

url = "http://127.0.0.1:8002/api/intelligence/analyze-ticker"
data = {
    "ticker": "KUYA.V",
    "source_type": "transcript",
    "input_text": "Test analyza s minimalnim textem pro validaci endpointu. Toto je testovaci vstup ktery ma pres padesat znaku aby prosla validace.",
    "investor_name": "Mark Gomes",
    "analysis_date": "2026-01-25"
}

print("Sending POST request...")
print(f"Data: {json.dumps(data, indent=2)}")
try:
    response = requests.post(url, json=data, timeout=60)
    print(f"\nStatus Code: {response.status_code}")
    if response.status_code == 200:
        print(f"Success: {json.dumps(response.json(), indent=2)}")
    else:
        print(f"Error Response: {response.text}")
except Exception as e:
    print(f"Exception: {type(e).__name__}: {e}")

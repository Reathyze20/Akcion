"""Ověří, že ANTHROPIC_API_KEY v backend/.env funguje.

Spusť z adresáře backend/:  python check_anthropic.py

Nic negeneruje (models.list() jen ověří autentizaci), takže to nestojí tokeny.
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv(".env")

key = os.environ.get("ANTHROPIC_API_KEY")
if not key:
    print("CHYBI ANTHROPIC_API_KEY v backend/.env")
    sys.exit(1)

print(f"klic nacten: {key[:14]}...{key[-4:]}")

try:
    import anthropic
except ModuleNotFoundError:
    print("chybi balicek — spust: python -m pip install anthropic")
    sys.exit(1)

client = anthropic.Anthropic(api_key=key)

try:
    models = client.models.list(limit=20)
except anthropic.AuthenticationError as e:
    print(f"AUTENTIZACE SELHALA — klic neplatny nebo odvolany:\n  {e.message}")
    sys.exit(1)
except anthropic.PermissionDeniedError as e:
    print(f"KLIC NEMA OPRAVNENI (chybi fakturace?):\n  {e.message}")
    sys.exit(1)
except Exception as e:
    print(f"{type(e).__name__}: {e}")
    sys.exit(1)

print("\nAUTENTIZACE OK. Dostupne modely:")
for m in models.data:
    print(f"  - {m.id}")

want = "claude-opus-5"
have = [m.id for m in models.data]
print(f"\n{want}: {'DOSTUPNY' if want in have else 'NEDOSTUPNY — pouzijeme jiny'}")

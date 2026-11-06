"""Check your RentCast key and see what it returns for an address (uses 1 of your monthly lookups).

PowerShell:
    $env:RENTCAST_API_KEY = "paste-your-key-here"
    python scripts/test_rentcast.py "123 Main St, Kansas City, MO 64111"
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import valuation  # noqa: E402

if not valuation.provider_configured():
    sys.exit('No key found. First run:  $env:RENTCAST_API_KEY = "your-key"')
if len(sys.argv) < 2:
    sys.exit('Give an address:  python scripts/test_rentcast.py "123 Main St, City, ST 12345"')

address = sys.argv[1]
result = valuation.fetch_avm(address)
if "error" in result:
    code = result["error"]
    hints = {
        401: "RentCast rejected the key. Check it was copied completely.",
        404: "RentCast couldn't find that address. Try the full street, city, state and ZIP.",
        429: "Too many requests or you hit your plan limit.",
    }
    sys.exit(f"Lookup failed ({code}). {hints.get(code, '')}")
print(f"Address:  {address}")
print(f"Estimate: ${result['price']:,.0f}")
if result.get("low") and result.get("high"):
    print(f"Range:    ${result['low']:,.0f} to ${result['high']:,.0f}")
print("The key works. Add it to Railway as RENTCAST_API_KEY.")

"""IRS business mileage rates and money formatting.

The rate depends on the date of the trip: it changes every January, and the IRS can change it mid-year
(it did on July 1, 2026). To add a new rate, add one line to RATES: (first day it applies, dollars per mile).
Please double check new rates against the IRS announcement before adding them.
"""
from datetime import date, datetime

RATES = [
    ("2022-01-01", 0.585),
    ("2022-07-01", 0.625),
    ("2023-01-01", 0.655),
    ("2024-01-01", 0.670),
    ("2025-01-01", 0.700),
    ("2026-01-01", 0.725),
    ("2026-07-01", 0.760),
]


def rate_for(when=None):
    """Dollars per business mile on a given day (a date, a 'YYYY-MM-DD' string, or None for today)."""
    if when is None or when == "":
        day = date.today().isoformat()
    elif isinstance(when, (date, datetime)):
        day = when.strftime("%Y-%m-%d")
    else:
        day = str(when).strip()[:10]
    rate = RATES[0][1]
    for start, r in RATES:
        if day >= start:
            rate = r
    return rate


def rate_label(rate):
    """0.725 -> '$0.725', 0.7 -> '$0.70', 0.76 -> '$0.76'."""
    s = f"{float(rate):.3f}"
    if s.endswith("0"):
        s = s[:-1]
    return "$" + s


def usd(value, decimals=0):
    """Money with the minus sign in front: -154 -> '-$154', 1234.5 -> '$1,235'."""
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        v = 0.0
    body = f"{abs(v):,.{int(decimals)}f}"
    if float(body.replace(",", "")) == 0:
        return "$" + body          # never show "-$0"
    return ("-$" if v < 0 else "$") + body

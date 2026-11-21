"""A gentle estimate of a homeowner's remaining mortgage, for people who do not know their exact numbers yet.

Real loan balances are private, so nothing here is looked up. From what they paid, when they bought and about how much
they put down, we assume a standard 30 year fixed loan at the typical rate for that year and work out where the balance
would be today. It is always shown as an estimate, and one tap replaces it with their real numbers."""
from datetime import date, datetime

# Typical 30 year fixed rate by year of purchase (rounded yearly averages, for estimating only)
TYPICAL_RATE = {
    1995: 7.9, 1996: 7.8, 1997: 7.6, 1998: 6.9, 1999: 7.4, 2000: 8.1, 2001: 7.0, 2002: 6.5, 2003: 5.8, 2004: 5.8,
    2005: 5.9, 2006: 6.4, 2007: 6.3, 2008: 6.0, 2009: 5.0, 2010: 4.7, 2011: 4.5, 2012: 3.7, 2013: 4.0, 2014: 4.2,
    2015: 3.9, 2016: 3.7, 2017: 4.0, 2018: 4.5, 2019: 3.9, 2020: 3.1, 2021: 3.0, 2022: 5.3, 2023: 6.8, 2024: 6.7,
    2025: 6.6, 2026: 6.3,
}
DOWN_CHOICES = (("3.5", "3.5% (FHA)"), ("5", "5%"), ("10", "About 10% (typical)"), ("20", "20% or more"))


def typical_rate(year):
    years = sorted(TYPICAL_RATE)
    year = max(years[0], min(years[-1], int(year)))
    return TYPICAL_RATE[year]


def _payment(loan, rate_pct, months=360):
    r = rate_pct / 100.0 / 12.0
    if r == 0:
        return loan / months
    return loan * r / (1 - (1 + r) ** -months)


def estimate(price, bought, down_pct=10.0, today=None):
    """Return {'balance','rate','payment','term','start','original'} or None when the inputs do not make sense.
    `bought` is a date, an ISO date string, or a four digit year."""
    today = today or date.today()
    try:
        price = float(str(price).replace("$", "").replace(",", ""))
        down = float(down_pct)
    except (TypeError, ValueError):
        return None
    if isinstance(bought, str):
        s = bought.strip()
        try:
            bought = datetime.strptime(s[:10], "%Y-%m-%d").date() if len(s) >= 8 else date(int(s), 6, 1)
        except ValueError:
            return None
    elif isinstance(bought, int):
        bought = date(bought, 6, 1)
    if not isinstance(bought, date) or price <= 0 or not (0 <= down < 100):
        return None
    if bought > today or bought.year < 1990:
        return None
    original = price * (1 - down / 100.0)
    rate = typical_rate(bought.year)
    pay = _payment(original, rate)
    n = min(360, max(0, (today.year - bought.year) * 12 + (today.month - bought.month)))
    r = rate / 100.0 / 12.0
    if n >= 360:
        bal = 0.0
    elif r == 0:
        bal = original - pay * n
    else:
        bal = original * (1 + r) ** n - pay * (((1 + r) ** n - 1) / r)
    return {"balance": round(max(bal, 0.0)), "rate": rate, "payment": round(pay), "term": 30,
            "start": bought.isoformat(), "original": round(original)}

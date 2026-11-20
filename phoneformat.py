"""Friendly phone numbers: 7852491464 -> (785) 249-1464. Anything unusual is left exactly as typed."""
import re


def pretty_phone(value):
    s = (value or "").strip()
    if not s:
        return ""
    digits = re.sub(r"\D", "", s)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10 and re.fullmatch(r"[\d\s().\-+]+", s):
        return "(%s) %s-%s" % (digits[:3], digits[3:6], digits[6:])
    return s

"""Size bands and a rough VAT-registration prior, from Companies House fields only.

The prior is a guide for prioritising and for interpreting 'not found' — never evidence for a
specific company. ~5.18M active companies vs ~2.18M VAT registrations (incl. sole traders), so at
most ~42% of active companies can be registered; medium/large trading companies almost all are.
"""
from __future__ import annotations


def size_band(cat: str) -> str:
    c = (cat or "").upper()
    if "DORMANT" in c:
        return "dormant"
    if "NO ACCOUNTS" in c:
        return "no_accounts_yet"
    if "MICRO" in c:
        return "micro"
    if any(k in c for k in ("TOTAL EXEMPTION", "UNAUDITED", "SMALL", "AUDIT EXEMPTION")):
        return "small"
    if any(k in c for k in ("FULL", "GROUP", "MEDIUM")):
        return "medium_large"
    return "other"


def likely_vat(band: str, charges: str | int | None = None) -> str:
    """very_likely | likely | possible | unlikely | unknown"""
    if band == "dormant":
        return "unlikely"
    if band == "medium_large":
        return "very_likely"
    try:
        has_charge = int(charges or 0) > 0
    except ValueError:
        has_charge = False
    if band == "small" or has_charge:
        return "likely"
    if band == "micro":
        return "possible"
    return "unknown"


LIKELY = {"very_likely", "likely"}

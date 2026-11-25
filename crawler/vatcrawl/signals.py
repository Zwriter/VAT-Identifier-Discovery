"""
Registration evidence from a company's own website, without the number itself.

  registered      "All prices exclude VAT", "£50 + VAT", "ex VAT", "excl. VAT", "plus VAT",
                  "inc VAT", "VAT registered", "VAT invoice"
  not_registered  "not VAT registered", "not registered for VAT", "no VAT is charged",
                  "VAT not applicable", "below the VAT threshold"

Observed: Nettex.io (VAT-registered, in Peppol) shows "All prices exclude VAT" but no VAT number.
Only trusted when the site is confirmed to be the company's (name or company number on it):
a wrongly matched domain (e.g. a school's site for 'Meadgate Pool Ltd') must not produce evidence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

NOT_REGISTERED = re.compile(
    r"\bnot\s+(?:currently\s+|yet\s+)?(?:VAT[\s-]?registered|registered\s+for\s+VAT)\b"
    r"|\bno\s+VAT\s+(?:is\s+|will\s+be\s+)?(?:charged|applicable|added|payable)\b"
    r"|\bVAT\s+(?:is\s+)?not\s+(?:charged|applicable|added)\b"
    r"|\bbelow\s+the\s+VAT\s+(?:registration\s+)?threshold\b",
    re.I)

REGISTERED = re.compile(
    r"\b(?:prices?|rates?|fees?|costs?)\b[^.\n]{0,40}?\b(?:exclud\w*|exclusive\s+of|excl\.?|ex\.?|plus|includ\w*|inclusive\s+of|incl?\.?)\s+(?:of\s+)?VAT\b"
    r"|(?:£|GBP)\s?\d[\d,.]*\s*(?:\+|plus|ex\.?|excl\.?|exc\.?|inc\.?|incl\.?)\s*VAT\b"
    r"|\b(?:ex|excl|exc)\.?\s+VAT\b"
    r"|\+\s?VAT\b"
    r"|\b(?<!not )VAT[\s-]registered\b"
    r"|\bVAT\s+invoices?\b",
    re.I)


@dataclass
class Signal:
    kind: str        # registered | not_registered
    text: str        # the phrase with a little context
    url: str


def _ctx(text: str, m: re.Match, pad: int = 60) -> str:
    return " ".join(text[max(0, m.start() - pad): m.end() + pad].split())


def find_signal(pages: list[tuple[str, str]]) -> Signal | None:
    """Explicit 'not registered' wins over pricing phrases (it is the more specific statement)."""
    first_reg = None
    for url, text in pages:
        m = NOT_REGISTERED.search(text)
        if m:
            return Signal("not_registered", _ctx(text, m), url)
        if first_reg is None:
            m = REGISTERED.search(text)
            if m:
                first_reg = Signal("registered", _ctx(text, m), url)
    return first_reg

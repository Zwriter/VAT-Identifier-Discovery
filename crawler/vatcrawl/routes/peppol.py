"""
Route 1: look the company up in the UK extract of the Peppol Directory (peppol_uk.csv,
produced by peppol_uk_fast.py). Offline and free.

Peppol has no postcode in our extract, so a match here is a *name* match: it is only
accepted as a candidate and must be confirmed by HMRC (whose returned address is then
compared with Companies House). Names that map to more than one VAT number are skipped.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from ..core import vat as V


class PeppolIndex:
    def __init__(self, csv_path: str | Path):
        self.by_name: dict[str, set[str]] = defaultdict(set)
        self.rows = 0
        with open(csv_path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                v = V.normalise_vat(r.get("gb_vat", "") or "")
                if not v or not r.get("name"):
                    continue
                self.by_name[V.name_core(r["name"])].add(v)
                self.rows += 1

    def lookup(self, name: str) -> tuple[str | None, str]:
        """Return (vat, reason). reason: peppol_name_match | not_in_peppol | ambiguous_name"""
        vats = self.by_name.get(V.name_core(name), set())
        if not vats:
            return None, "not_in_peppol"
        if len(vats) > 1:
            return None, "ambiguous_name"
        return next(iter(vats)), "peppol_name_match"

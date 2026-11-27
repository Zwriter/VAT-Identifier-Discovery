#!/usr/bin/env python3
"""
Scan downloaded public-record files for UK VAT numbers and report numbers you can quote.

Works on CSV, XLSX, JSON (including OCDS procurement data) and plain text/HTML files.
For each file it reports:
  - rows / records
  - column headers (CSV/XLSX) and any header that mentions VAT, registration or company number
  - VAT-like strings found anywhere, and how many pass the HMRC checksum
  - for JSON/OCDS: which identifier schemes appear (e.g. GB-COH, GB-PPON, GB-VAT) and how often

Usage (from crawler/):
  python scripts/scan_files_for_vat.py ../unseen_data/public_records/councils/*.csv
  python scripts/scan_files_for_vat.py ../unseen_data/public_records/find_tender.json
  python scripts/scan_files_for_vat.py ../unseen_data/public_records/*  --out ../data/public_records_scan.csv
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vatcrawl.core import vat as V  # noqa: E402

RAW_VATLIKE = re.compile(r"(?<![A-Z0-9])(?:GB)?\s?\d{3}\s?\d{4}\s?\d{2}(?!\d)", re.I)
HEADER_HINT = re.compile(r"vat|registration|reg\.?\s*no|company\s*(no|number)|crn|supplier\s*id", re.I)


def scan_text(text: str) -> tuple[int, int, list[str]]:
    """(vat-like strings, labelled/prefixed checksum-valid VATs, examples)"""
    raw = len(RAW_VATLIKE.findall(text))
    cands = V.find_vat_candidates(text)
    return raw, len(cands), [c.raw for c in cands[:5]]


def _valid_in_vat_columns(headers: list[str], rows: list[list[str]]) -> int:
    """Cells in columns whose header mentions VAT number/registration that are valid GB VAT numbers.
    (Columns like 'Irrecoverable VAT' hold amounts; those never pass the checksum.)"""
    idx = [i for i, h in enumerate(headers) if re.search(r"vat", h, re.I)]
    n = 0
    for r in rows:
        for i in idx:
            if i < len(r) and V.normalise_vat(r[i] or ""):
                n += 1
    return n


def walk_json(obj, schemes: Counter):
    if isinstance(obj, dict):
        if "scheme" in obj and ("id" in obj or "value" in obj):
            schemes[str(obj["scheme"])] += 1
        for v in obj.values():
            walk_json(v, schemes)
    elif isinstance(obj, list):
        for v in obj:
            walk_json(v, schemes)


def scan_file(path: Path) -> dict:
    out = {"file": str(path), "type": path.suffix.lower().lstrip("."), "records": "", "headers": "",
           "vat_headers": "", "vat_column_valid": 0, "vat_like_strings": 0, "valid_vat_candidates": 0,
           "examples": "", "id_schemes": ""}
    suf = path.suffix.lower()
    try:
        if suf in (".csv", ".tsv"):
            raw = path.read_bytes().decode("utf-8-sig", "replace")
            dialect = "\t" if suf == ".tsv" else ","
            rows = list(csv.reader(raw.splitlines(), delimiter=dialect))
            if rows:
                headers = [h.strip() for h in rows[0]]
                out["headers"] = " | ".join(headers)[:500]
                out["vat_headers"] = " | ".join(h for h in headers if HEADER_HINT.search(h))
                out["records"] = len(rows) - 1
                out["vat_column_valid"] = _valid_in_vat_columns(headers, rows[1:])
            text = raw
        elif suf in (".xlsx", ".xls"):
            import pandas as pd
            df = pd.read_excel(path, dtype=str)
            out["headers"] = " | ".join(map(str, df.columns))[:500]
            out["vat_headers"] = " | ".join(str(h) for h in df.columns if HEADER_HINT.search(str(h)))
            out["records"] = len(df)
            out["vat_column_valid"] = _valid_in_vat_columns([str(c) for c in df.columns],
                                                            df.fillna("").astype(str).values.tolist())
            text = df.to_csv(index=False)
        elif suf == ".json":
            text = path.read_text(encoding="utf-8", errors="replace")
            data = json.loads(text)
            schemes: Counter = Counter()
            walk_json(data, schemes)
            out["id_schemes"] = ", ".join(f"{k}={v}" for k, v in schemes.most_common(10))
            if isinstance(data, dict):
                for key in ("releases", "records", "results", "items", "notices"):
                    if isinstance(data.get(key), list):
                        out["records"] = len(data[key])
                        break
            elif isinstance(data, list):
                out["records"] = len(data)
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # keep going on bad files
        out["examples"] = f"ERROR {type(e).__name__}: {e}"
        return out
    raw, valid, ex = scan_text(text)
    out.update(vat_like_strings=raw, valid_vat_candidates=valid, examples=" ; ".join(ex))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out", help="Write a CSV summary here")
    a = ap.parse_args(argv)
    files = [Path(p) for pat in a.paths for p in (glob.glob(pat) or [pat]) if Path(p).is_file()]
    if not files:
        sys.exit("No files found")
    results = [scan_file(f) for f in files]
    for r in results:
        print(f"\n== {r['file']}")
        print(f"   records: {r['records']}   VAT-ish headers: {r['vat_headers'] or '(none)'}")
        if r["id_schemes"]:
            print(f"   identifier schemes: {r['id_schemes']}")
        print(f"   valid VATs in VAT columns: {r['vat_column_valid']}   VAT-like strings: {r['vat_like_strings']}   "
              f"checksum-valid labelled/GB VATs in text: {r['valid_vat_candidates']}")
        if r["examples"]:
            print(f"   examples: {r['examples']}")
    tot_col = sum(r["vat_column_valid"] for r in results)
    tot_valid = sum(r["valid_vat_candidates"] for r in results)
    print(f"\nFiles: {len(results)}   valid VATs in VAT columns: {tot_col}   in text: {tot_valid}")
    if a.out:
        with open(a.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            w.writeheader()
            w.writerows(results)
        print(f"Summary saved: {a.out}")


if __name__ == "__main__":
    main()

"""
Shrink the Companies House BasicCompanyData file(s) to what matters for VAT discovery.

Keeps the columns that help find or attribute a VAT number (see the column-importance scoring
in the Findings note), adds derived fields, and optionally drops rows you will never sample.
Reads in chunks, so a 2 GB file needs well under 1 GB of memory.

Kept columns
  identity / attribution : CompanyNumber, CompanyName, RegAddress.AddressLine1, RegAddress.AddressLine2,
                           RegAddress.PostTown, RegAddress.PostCode, PreviousName_1.CompanyName
  registration likelihood: CompanyStatus, CompanyCategory, Accounts.AccountCategory, SICCode.SicText_1,
                           IncorporationDate, Mortgages.NumMortCharges, Accounts.LastMadeUpDate
Derived
  company_number_norm, size_band, postcode_district, name_core, likely_vat (rough prior, not ground truth)

Usage
  python -m vatcrawl.slim_ch --ch ../unseen_data/BasicCompanyDataAsOneFile-2026-11-01.csv \
      --out ../data/ch_slim.csv --active-only
  Optional: --drop-dormant  --drop-other-band  --drop-strike-off
"""
from __future__ import annotations

import argparse
import glob
import json
import time

import pandas as pd

from . import vat as V
from .pipeline import size_band

KEEP = [
    "CompanyNumber", "CompanyName",
    "RegAddress.AddressLine1", "RegAddress.AddressLine2", "RegAddress.PostTown", "RegAddress.PostCode",
    "PreviousName_1.CompanyName",
    "CompanyStatus", "CompanyCategory", "Accounts.AccountCategory", "SICCode.SicText_1",
    "IncorporationDate", "Mortgages.NumMortCharges", "Accounts.LastMadeUpDate",
]


def likely_vat(band: str, charges: str) -> str:
    """Rough prior from Companies House alone. A guide for prioritising and for the denominator,
    never evidence for a specific company."""
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ch", nargs="+", required=True, help="Companies House CSV file(s) or glob")
    ap.add_argument("--out", default="ch_slim.csv")
    ap.add_argument("--active-only", action="store_true", help="Keep CompanyStatus == 'Active' only")
    ap.add_argument("--drop-strike-off", action="store_true", help="Drop 'Active - Proposal to Strike off'")
    ap.add_argument("--drop-dormant", action="store_true")
    ap.add_argument("--drop-other-band", action="store_true", help="Drop unusual account types (band 'other')")
    ap.add_argument("--chunksize", type=int, default=200_000)
    a = ap.parse_args(argv)

    files = sorted({p for pat in a.ch for p in glob.glob(pat)})
    if not files:
        raise SystemExit("No input files matched --ch")
    t0, rows_in, rows_out, first = time.time(), 0, 0, True
    by_status, by_band = {}, {}

    for path in files:
        reader = pd.read_csv(path, dtype=str, usecols=lambda c: c.strip() in KEEP,
                             chunksize=a.chunksize, keep_default_na=False)
        for chunk in reader:
            chunk.columns = [c.strip() for c in chunk.columns]
            rows_in += len(chunk)
            for k, v in chunk["CompanyStatus"].value_counts().items():
                by_status[k] = by_status.get(k, 0) + int(v)

            if a.active_only:
                chunk = chunk[chunk["CompanyStatus"] == "Active"]
            elif a.drop_strike_off:
                chunk = chunk[~chunk["CompanyStatus"].str.contains("Strike off", case=False, na=False)]

            chunk = chunk.copy()
            chunk["size_band"] = chunk["Accounts.AccountCategory"].map(size_band)
            if a.drop_dormant:
                chunk = chunk[chunk["size_band"] != "dormant"]
            if a.drop_other_band:
                chunk = chunk[chunk["size_band"] != "other"]

            chunk["company_number_norm"] = chunk["CompanyNumber"].map(V.normalise_company_number)
            chunk["postcode_district"] = chunk["RegAddress.PostCode"].map(lambda p: V.postcode_district(p) or "")
            chunk["name_core"] = chunk["CompanyName"].map(V.name_core)
            chunk["likely_vat"] = [likely_vat(b, c) for b, c in zip(chunk["size_band"], chunk["Mortgages.NumMortCharges"])]

            for k, v in chunk["size_band"].value_counts().items():
                by_band[k] = by_band.get(k, 0) + int(v)
            chunk.to_csv(a.out, mode="w" if first else "a", header=first, index=False)
            first = False
            rows_out += len(chunk)
            print(f"  {rows_in:,} read, {rows_out:,} kept ({time.time() - t0:.0f}s)", flush=True)

    meta = {"inputs": files, "rows_in": rows_in, "rows_out": rows_out,
            "filters": {k: getattr(a, k) for k in ("active_only", "drop_strike_off", "drop_dormant", "drop_other_band")},
            "status_counts_in": by_status, "size_band_counts_out": by_band,
            "seconds": round(time.time() - t0)}
    with open(a.out.rsplit(".", 1)[0] + "_meta.json", "w") as f:
        json.dump(meta, f, indent=2)
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()

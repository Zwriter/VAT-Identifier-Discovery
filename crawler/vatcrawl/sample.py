"""
Draw a frozen, stratified random sample from the Companies House BasicCompanyData CSV(s).

Strata = size bands from the accounts category (dormant, no accounts yet, micro, small, medium/large),
so small strata (medium/large companies) aren't swamped by micro companies. The seed and the per-band
counts are printed and written next to the sample so the draw can be repeated exactly.

Usage:
  python -m vatcrawl.sample --ch ../unseen_data/BasicCompanyDataAsOneFile-2026-11-01.csv --per-band 10 --seed 42 --out sample.csv
"""
from __future__ import annotations

import argparse
import glob
import json

import pandas as pd

from .pipeline import size_band

COLS = ["CompanyName", "CompanyNumber", "RegAddress.AddressLine1", "RegAddress.PostTown", "RegAddress.PostCode",
        "CompanyCategory", "CompanyStatus", "IncorporationDate", "Accounts.AccountCategory", "SICCode.SicText_1"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ch", nargs="+", required=True, help="Companies House CSV file(s) or glob")
    ap.add_argument("--per-band", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--active-only", action="store_true", help="Keep only CompanyStatus == Active")
    ap.add_argument("--out", default="sample.csv")
    args = ap.parse_args(argv)

    files = sorted({p for pat in args.ch for p in glob.glob(pat)})
    frames = []
    for p in files:
        # read only the needed columns (headers in the CH file can carry leading spaces)
        df = pd.read_csv(p, dtype=str, usecols=lambda c: c.strip() in COLS)
        df.columns = [c.strip() for c in df.columns]
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    if args.active_only:
        df = df[df["CompanyStatus"] == "Active"]
    df["size_band"] = df["Accounts.AccountCategory"].map(size_band)

    parts = []
    for band, g in df.groupby("size_band"):
        parts.append(g.sample(min(args.per_band, len(g)), random_state=args.seed))
    sample = pd.concat(parts).sample(frac=1, random_state=args.seed).reset_index(drop=True)
    sample.to_csv(args.out, index=False)

    meta = {"files": files, "population": len(df), "seed": args.seed, "per_band": args.per_band,
            "population_by_band": df["size_band"].value_counts().to_dict(),
            "sample_by_band": sample["size_band"].value_counts().to_dict(),
            "note": "Companies House CSVs are split alphabetically; use all parts for a representative draw."}
    with open(args.out.rsplit(".", 1)[0] + "_meta.json", "w") as f:
        json.dump(meta, f, indent=2)
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()

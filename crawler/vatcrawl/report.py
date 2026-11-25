"""
Turn results.csv (after HMRC checks are filled in) into final outcomes and the Part 2 tables.

Fill these columns by hand from HMRC's checker (or the API) for every found_unverified row:
  hmrc_status   valid | not_found
  hmrc_name     name HMRC returned
  hmrc_postcode postcode HMRC returned
For 'unknown' rows you may fill registration_evidence (e.g. "accounts: reserves +£292k", "job ad: <url>").

Final outcomes:
  found_verified          HMRC valid AND names match
  found_wrong_company     HMRC valid but a different business  -> counts as a false positive
  found_invalid           HMRC not found                       -> counts as a false positive
  registered_not_found    unknown + registration evidence
  probably_not_registered / unknown  unchanged

Usage:
  python -m vatcrawl.report --results results.csv --out results_final.csv
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict

from . import vat as V


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, c - h), min(1.0, c + h))


def finalise(r: dict) -> dict:
    o = r["outcome"]
    if o == "found_unverified":
        st = (r.get("hmrc_status") or "").strip().lower()
        if st == "valid":
            r["name_match"] = str(V.names_match(r["company_name"], r.get("hmrc_name", "")))
            d1, d2 = V.postcode_district(r.get("postcode", "")), V.postcode_district(r.get("hmrc_postcode", ""))
            r["postcode_district_match"] = str(bool(d1 and d1 == d2))
            r["outcome"] = "found_verified" if r["name_match"] == "True" else "found_wrong_company"
        elif st in ("not_found", "invalid"):
            r["outcome"] = "found_invalid"
        # else: still unverified -> excluded from reported finds
    elif o == "unknown" and (r.get("registration_evidence") or "").strip():
        r["outcome"] = "registered_not_found"
    return r


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", default="results_final.csv")
    a = ap.parse_args(argv)
    rows = [finalise(r) for r in csv.DictReader(open(a.results, newline="", encoding="utf-8"))]
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    n = len(rows)
    print(f"\nCompanies: {n}\n")
    print("Outcomes:")
    for k, v in Counter(r["outcome"] for r in rows).most_common():
        print(f"  {k:26} {v:4}  ({v / n:.0%})")

    print("\nOutcome by size band:")
    by = defaultdict(Counter)
    for r in rows:
        by[r["size_band"]][r["outcome"]] += 1
    for band, c in sorted(by.items()):
        tot = sum(c.values())
        print(f"  {band:16} n={tot:3}  " + ", ".join(f"{k}={v}" for k, v in c.most_common()))

    print("\nPer route (checked candidates only):")
    for route in ("peppol", "website", "search"):
        cand = [r for r in rows if r["route"] == route and r["outcome"].startswith("found_")
                and r["outcome"] != "found_unverified"]
        ok = sum(r["outcome"] == "found_verified" for r in cand)
        print(f"  {route:8} checked={len(cand):3} verified={ok:3}")

    checked = [r for r in rows if r["outcome"] in ("found_verified", "found_wrong_company", "found_invalid")]
    if checked:
        k_inv = sum(r["outcome"] == "found_invalid" for r in checked)
        valid = [r for r in checked if r["outcome"] != "found_invalid"]
        k_wrong = sum(r["outcome"] == "found_wrong_company" for r in valid)
        lo, hi = wilson(k_inv, len(checked))
        print(f"\nInvalid at HMRC:       {k_inv}/{len(checked)} = {k_inv / len(checked):.0%}  (95% CI {lo:.0%}-{hi:.0%})")
        if valid:
            lo, hi = wilson(k_wrong, len(valid))
            print(f"Valid but wrong company: {k_wrong}/{len(valid)} = {k_wrong / len(valid):.0%}  (95% CI {lo:.0%}-{hi:.0%})")
    pending = sum(r["outcome"] == "found_unverified" for r in rows)
    if pending:
        print(f"\n{pending} candidates still unverified (not counted as found).")
    print(f"\nSaved {a.out}")


if __name__ == "__main__":
    main()

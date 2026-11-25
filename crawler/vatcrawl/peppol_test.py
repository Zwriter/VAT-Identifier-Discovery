"""
Masked-Peppol test: can the crawler rediscover VAT numbers we already know?

  build     Match Peppol UK entries to Companies House (unique normalised-name match only),
            draw a random set, and write
              - a sample file in Companies House format WITHOUT the VAT number (crawler input)
              - a truth file with the hidden VAT number (never given to the crawler)
  evaluate  Compare the crawler's results with the truth:
              recall            correct / tested
              precision         correct / (correct + wrong number)
              wrong-number rate wrong / (correct + wrong)   <- the dangerous error
            broken down by size band, route and website failure reason, with 95% intervals,
            plus a list of disagreements to check on HMRC (Peppol itself can be stale: in the
            17-check HMRC sample, 2 Peppol numbers were no longer registered).

Bias to state in the write-up: Peppol companies are e-invoicing adopters (more B2B, more
digitally organised), so recall here is an optimistic upper bound for the long tail.

Usage (from crawler/):
  python -m vatcrawl.peppol_test build --peppol ../data/peppol_uk.csv --ch ../data/ch_slim.csv \
      --n 40 --seed 7 --out-sample ../data/peppol_test_sample.csv --out-truth ../data/peppol_test_truth.csv
  python -m vatcrawl.find_domains --sample ../data/peppol_test_sample.csv --out ../data/peppol_test_domains.csv
  python -m vatcrawl.pipeline --sample ../data/peppol_test_sample.csv --domains ../data/peppol_test_domains.csv \
      --routes website --out ../data/peppol_test_results.csv --log ../data/peppol_test_log.jsonl
  python -m vatcrawl.peppol_test evaluate --results ../data/peppol_test_results.csv --truth ../data/peppol_test_truth.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import Counter, defaultdict

import pandas as pd

from . import vat as V
from .report import wilson

CH_COLS = ["CompanyName", "CompanyNumber", "RegAddress.AddressLine1", "RegAddress.PostTown", "RegAddress.PostCode",
           "CompanyCategory", "CompanyStatus", "IncorporationDate", "Accounts.AccountCategory", "SICCode.SicText_1",
           "Mortgages.NumMortCharges", "Accounts.LastMadeUpDate", "size_band", "likely_vat", "name_core"]
TESTY = re.compile(r"\btest\b|t[äa]st|demo|sandbox", re.I)


# ----------------------------------------------------------------------------- build
def build(a):
    # 1. Peppol: one VAT per normalised name (names with several VATs are ambiguous -> skipped)
    by_name: dict[str, set[str]] = defaultdict(set)
    pnames: dict[str, str] = {}
    pdate: dict[str, str] = {}
    for r in csv.DictReader(open(a.peppol, newline="", encoding="utf-8")):
        v = V.normalise_vat(r.get("gb_vat", "") or "")
        if not v or not r.get("name") or TESTY.search(r["name"]):
            continue
        k = V.name_core(r["name"])
        by_name[k].add(v)
        pnames.setdefault(k, r["name"])
        pdate.setdefault(k, r.get("regdate", ""))
    unique = {k: next(iter(vs)) for k, vs in by_name.items() if len(vs) == 1}
    print(f"Peppol names with exactly one VAT: {len(unique):,}")

    # 2. Companies House: stream, keep only rows whose name_core is a Peppol name
    hits: dict[str, list[dict]] = defaultdict(list)
    reader = pd.read_csv(a.ch, dtype=str, keep_default_na=False, chunksize=300_000,
                         usecols=lambda c: c in CH_COLS)
    for chunk in reader:
        if "name_core" not in chunk:
            chunk["name_core"] = chunk["CompanyName"].map(V.name_core)
        m = chunk[chunk["name_core"].isin(unique)]
        for row in m.to_dict("records"):
            hits[row["name_core"]].append(row)
    matched = {k: rows[0] for k, rows in hits.items() if len(rows) == 1}
    print(f"Unique Peppol <-> Companies House name matches: {len(matched):,} "
          f"(ambiguous: {sum(len(r) > 1 for r in hits.values()):,})")
    if a.exclude_dormant:
        matched = {k: r for k, r in matched.items() if r.get("size_band") != "dormant"}

    # 3. Random draw
    keys = sorted(matched)
    random.Random(a.seed).shuffle(keys)
    keys = keys[: a.n]
    sample = [matched[k] for k in keys]
    pd.DataFrame(sample).drop(columns=["name_core"], errors="ignore").to_csv(a.out_sample, index=False)
    with open(a.out_truth, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["company_number", "company_name", "true_vat", "peppol_name", "peppol_regdate", "size_band"])
        for k, r in zip(keys, sample):
            w.writerow([V.normalise_company_number(r["CompanyNumber"]), r["CompanyName"], unique[k],
                        pnames[k], pdate[k], r.get("size_band", "")])
    meta = {"seed": a.seed, "n": len(sample), "peppol_unique_names": len(unique), "unique_matches": len(matched),
            "by_band": Counter(r.get("size_band", "") for r in sample),
            "caveat": "Peppol companies are e-invoicing adopters; recall is an optimistic upper bound.",
            "note": "Name-only matching; ~1 in 15 such matches was the wrong company in the HMRC spot-check."}
    with open(a.out_truth.rsplit(".", 1)[0] + "_meta.json", "w") as f:
        json.dump(meta, f, indent=2, default=dict)
    print(json.dumps(meta, indent=2, default=dict))
    print(f"\nCrawler input: {a.out_sample}   (no VAT numbers)\nHidden truth:  {a.out_truth}")


# -------------------------------------------------------------------------- evaluate
def _ci(k, n):
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n:.0%} (95% CI {lo:.0%}-{hi:.0%})" if n else "n/a"


def evaluate(a):
    truth = {V.normalise_company_number(r["company_number"]): r
             for r in csv.DictReader(open(a.truth, newline="", encoding="utf-8"))}
    res = {V.normalise_company_number(r["company_number"]): r
           for r in csv.DictReader(open(a.results, newline="", encoding="utf-8"))}
    rows = []
    for num, t in truth.items():
        r = res.get(num)
        found = (r or {}).get("vat", "")
        if r is None:
            verdict = "not_run"
        elif not found:
            verdict = "not_found"
        elif found == t["true_vat"]:
            verdict = "correct"
        else:
            verdict = "wrong_number"
        rows.append({**t, "found_vat": found, "verdict": verdict,
                     "route": (r or {}).get("route", ""), "reason": (r or {}).get("reason", ""),
                     "website_reason": (r or {}).get("website_reason", ""),
                     "outcome": (r or {}).get("outcome", ""),
                     "site_identity": (r or {}).get("site_identity", ""),
                     "registration_evidence": (r or {}).get("registration_evidence", ""),
                     "domain": (r or {}).get("domain", ""), "source_url": (r or {}).get("source_url", ""),
                     "evidence": (r or {}).get("evidence", "")})

    tested = [r for r in rows if r["verdict"] != "not_run"]
    n = len(tested)
    c = sum(r["verdict"] == "correct" for r in tested)
    w = sum(r["verdict"] == "wrong_number" for r in tested)
    print(f"\nMasked-Peppol test: {n} companies tested ({len(rows) - n} not in results)\n")
    print(f"Recall (correct number found):      {_ci(c, n)}")
    print(f"Precision (correct / numbers given): {_ci(c, c + w)}")
    print(f"Wrong-number rate:                   {_ci(w, c + w)}   <- invisible errors")
    print(f"Not found:                           {_ci(n - c - w, n)}")

    def table(title, key):
        print(f"\n{title}:")
        groups = defaultdict(Counter)
        for r in tested:
            groups[r[key] or "-"][r["verdict"]] += 1
        for g, cnt in sorted(groups.items(), key=lambda x: -sum(x[1].values())):
            tot = sum(cnt.values())
            print(f"  {g:28} n={tot:3}  correct={cnt['correct']:3}  wrong={cnt['wrong_number']:2}  "
                  f"not_found={cnt['not_found']:3}")

    table("By size band", "size_band")
    table("By route that answered", "route")
    table("Website failure reason (why not found)", "website_reason")

    table("Outcome (all truth companies ARE registered)", "outcome")
    nf = [r for r in tested if r["verdict"] == "not_found"]
    reg_ok = sum(r["outcome"] == "registered_not_found" for r in nf)
    reg_bad = sum(r["outcome"] == "probably_not_registered" for r in nf)
    print(f"\nRegistration evidence on not-found companies: correctly 'registered' {reg_ok}/{len(nf)}; "
          f"wrongly 'not registered' {reg_bad}/{len(nf)}")
    unconf = sum(1 for r in tested if r["domain"] and r["site_identity"] == "unconfirmed")
    print(f"Domains crawled but site identity unconfirmed (likely wrong domain): {unconf}")

    no_domain = sum(1 for r in tested if not r["domain"])
    print(f"\nNo domain to crawl: {no_domain}/{n}  -> domain discovery is a bottleneck if this is large")

    wrong = [r for r in tested if r["verdict"] == "wrong_number"]
    if wrong:
        print("\nDisagreements — check BOTH numbers on HMRC (Peppol can be stale):")
        for r in wrong:
            print(f"  {r['company_number']} {r['company_name'][:35]:35} peppol={r['true_vat']} crawler={r['found_vat']}  {r['source_url']}")

    out = a.out or a.results.rsplit(".", 1)[0] + "_eval.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    print(f"\nPer-company evaluation saved: {out}")
    return {"n": n, "correct": c, "wrong": w}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--peppol", required=True)
    b.add_argument("--ch", required=True, help="ch_slim.csv (or a raw Companies House CSV)")
    b.add_argument("--n", type=int, default=40)
    b.add_argument("--seed", type=int, default=7)
    b.add_argument("--exclude-dormant", action="store_true")
    b.add_argument("--out-sample", default="peppol_test_sample.csv")
    b.add_argument("--out-truth", default="peppol_test_truth.csv")
    e = sub.add_parser("evaluate")
    e.add_argument("--results", required=True)
    e.add_argument("--truth", required=True)
    e.add_argument("--out")
    a = ap.parse_args(argv)
    return build(a) if a.cmd == "build" else evaluate(a)


if __name__ == "__main__":
    main()

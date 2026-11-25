"""
Run the routes in order for every company in a sample and write one result row per company.

  Route 1  Peppol lookup          (offline)
  Route 2  Company website + PDFs (needs a domain: --domains CSV, or found by Route 3)
  Route 3  Number-keyed search    (needs a backend: --search-csv or --search brave)
  Route 4  Registration evidence  (manual for the PoC: filled in later from accounts / job ads)

Outcomes:
  found_unverified        accepted candidate, waiting for HMRC (never reported as found)
  probably_not_registered dormant / strike-off / no accounts yet
  unknown                 with a reason code (no_website, site_no_vat, company_number_only, ...)
After HMRC checks (hmrc_status=valid + name match) found_unverified becomes found_verified;
"unknown" rows with registration evidence become registered_not_found.

Usage:
  python -m vatcrawl.run.pipeline --sample sample.csv --peppol ../peppol_uk.csv \
      --domains domains.csv --search-csv manual_search.csv --out results.csv
"""
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

from ..core import vat as V
from ..core.attribute import Target
from ..core.bands import LIKELY, likely_vat, size_band  # noqa: F401  (size_band re-exported)
from ..config import env_float, load_env
from ..web.fetch import Fetcher
from ..routes.peppol import PeppolIndex
from ..routes.search import BraveBackend, ManualBackend, run_search
from ..routes.website import crawl_site

FIELDS = ["company_number", "company_name", "postcode", "accounts_category", "status", "size_band",
          "outcome", "reason", "vat", "route", "evidence", "source_url", "context",
          "domain", "website_reason", "site_identity", "search_queries", "rejected_candidates",
          "hmrc_status", "hmrc_name", "hmrc_postcode", "name_match", "postcode_district_match",
          "registration_prior", "registration_evidence", "requests_made", "bytes_read", "seconds"]


def load_domains(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {V.normalise_company_number(r["company_number"]): r["domain"].strip()
                for r in csv.DictReader(f) if r.get("domain", "").strip()}


def process(row: dict, peppol: PeppolIndex | None, fetcher: Fetcher, domains: dict[str, str],
            backend, routes: set[str]) -> dict:
    t0 = time.time()
    req0, bytes0 = fetcher.requests_made, fetcher.bytes_read
    num = V.normalise_company_number(row["CompanyNumber"])
    fetcher.company = num
    target = Target(num, row["CompanyName"], row.get("RegAddress.PostCode", ""))
    cat = row.get("Accounts.AccountCategory", "")
    out = {k: "" for k in FIELDS}
    out.update(company_number=num, company_name=row["CompanyName"], postcode=target.postcode,
               accounts_category=cat, status=row.get("CompanyStatus", ""), size_band=size_band(cat),
               registration_prior=row.get("likely_vat") or likely_vat(size_band(cat), row.get("Mortgages.NumMortCharges")))
    rejected: list[str] = []

    def done(outcome, reason, **kw):
        out.update(outcome=outcome, reason=reason, **kw)
        out["rejected_candidates"] = "; ".join(rejected[:5])
        out["requests_made"] = fetcher.requests_made - req0
        out["bytes_read"] = fetcher.bytes_read - bytes0
        out["seconds"] = round(time.time() - t0, 1)
        return out

    # Route 1 — Peppol
    if "peppol" in routes and peppol:
        v, why = peppol.lookup(target.name)
        if v:
            return done("found_unverified", why, vat=v, route="peppol", evidence="peppol_name_match")

    # Route 3 first-pass for domain discovery happens inside the search route below
    search_out = None
    site_signal = None

    # Route 2 — website
    domain = domains.get(num, "")
    if "website" in routes and domain:
        out["domain"] = domain
        sr = crawl_site(fetcher, domain, target)
        out["website_reason"] = sr.reason
        out["site_identity"] = "confirmed" if sr.identity_confirmed else "unconfirmed"
        rejected += [f"{d.vat}:{d.reason}" for d in sr.rejected]
        if sr.decision:
            d = sr.decision
            return done("found_unverified", "website", vat=d.vat, route="website", evidence=d.evidence,
                        source_url=sr.source_url, context=d.context[:300])
        site_signal = sr.signal

    # Route 3 — search
    if "search" in routes and backend is not None:
        search_out = run_search(backend, fetcher, target)
        out["search_queries"] = search_out.queries_run
        rejected += [f"{d.vat}:{d.reason}" for d in search_out.rejected]
        if search_out.decision:
            d = search_out.decision
            return done("found_unverified", f"search_{search_out.via}", vat=d.vat, route="search",
                        evidence=d.evidence, source_url=search_out.source_url, context=d.context[:300])
        # a domain discovered by search can still be crawled
        if "website" in routes and not domain and search_out.candidate_domains:
            domain = search_out.candidate_domains[0]
            out["domain"] = domain + " (from search)"
            sr = crawl_site(fetcher, domain, target)
            out["website_reason"] = sr.reason
            if sr.decision:
                d = sr.decision
                return done("found_unverified", "website_from_search", vat=d.vat, route="website",
                            evidence=d.evidence, source_url=sr.source_url, context=d.context[:300])

    # Route 4 — registration evidence found on the company's own (identity-confirmed) site
    if site_signal is not None:
        ev = f'"{site_signal.text}" @ {site_signal.url}'
        if site_signal.kind == "not_registered":
            return done("probably_not_registered", "site_says_not_vat_registered", registration_evidence=ev)
        return done("registered_not_found", "site_mentions_vat_pricing", registration_evidence=ev)

    band = size_band(cat)
    status = (row.get("CompanyStatus") or "").lower()
    if band == "dormant":
        return done("probably_not_registered", "dormant")
    if "strike off" in status:
        return done("probably_not_registered", "strike_off")
    website_tried = "website" in routes and bool(domain)
    search_tried = "search" in routes and backend is not None
    if not website_tried and not search_tried:
        return done("unknown", "not_attempted")      # routes 2-3 never ran: says nothing about the company
    if not domain:
        return done("unknown", "no_website_found")   # search ran but found no usable domain
    return done("unknown", out["website_reason"] or "not_found")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", required=True, help="Sample CSV (Companies House columns)")
    ap.add_argument("--peppol", help="peppol_uk.csv from peppol_uk_fast.py")
    ap.add_argument("--domains", help="CSV company_number,domain (manually or otherwise found)")
    ap.add_argument("--search-csv", help="Manual search results CSV: query,rank,url,title,snippet")
    ap.add_argument("--search", choices=["none", "brave"], default="none")
    ap.add_argument("--routes", default="peppol,website,search")
    ap.add_argument("--out", default="results.csv")
    ap.add_argument("--log", default="crawl_log.jsonl")
    load_env()
    ap.add_argument("--delay", type=float, default=env_float("CRAWL_DELAY", 1.0),
                    help="Seconds between requests to the same host (default from CRAWL_DELAY in .env)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)

    routes = set(args.routes.split(","))
    peppol = PeppolIndex(args.peppol) if args.peppol and "peppol" in routes else None
    backend = ManualBackend(args.search_csv) if args.search_csv else (BraveBackend() if args.search == "brave" else None)
    fetcher = Fetcher(log_path=args.log, delay=args.delay)
    domains = load_domains(args.domains)

    with open(args.sample, newline="", encoding="utf-8-sig") as f:
        rows = [{k.strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]
    if args.limit:
        rows = rows[: args.limit]

    with open(args.out, "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=FIELDS)
        w.writeheader()
        for i, row in enumerate(rows, 1):
            res = process(row, peppol, fetcher, domains, backend, routes)
            w.writerow(res)
            fo.flush()
            print(f"[{i}/{len(rows)}] {res['company_number']} {res['company_name'][:40]:40} "
                  f"-> {res['outcome']} ({res['reason']}) {res['vat']}")
    print(f"Saved {args.out}; request log {args.log}")


if __name__ == "__main__":
    main()

"""
Find each sampled company's own website with the Brave Search API -> domains.csv (input for Route 2).

Query: "<company name without Ltd>" <post town>. Directory/aggregator sites are skipped, and a domain
is accepted only if it resembles the company name (tokens or initials in the domain label).

A wrong domain is low-risk: the website route still only accepts a VAT number that sits next to the
target's own company number or postcode + name. A wrong domain just ends in 'site_no_vat'.

Usage (from crawler/, venv active, BRAVE_API_KEY in .env):
  python -m vatcrawl.find_domains --sample ../data/sample.csv --out ../data/domains.csv --skip-dormant
"""
from __future__ import annotations

import argparse
import csv
import re
from urllib.parse import urlparse

from . import vat as V
from .bands import size_band
from .search import DIRECTORY_DOMAINS, BraveBackend

GENERIC = {"LTD", "LIMITED", "PLC", "LLP", "LP", "CIC", "CO", "COMPANY", "UK", "GB", "GROUP", "HOLDINGS",
           "HOLDING", "SERVICES", "SERVICE", "SOLUTIONS", "INTERNATIONAL", "AND", "THE", "OF", "EUROPE",
           "TRADING", "ENTERPRISES", "INVESTMENTS", "PROPERTIES", "PROPERTY", "CONSULTING", "MANAGEMENT"}
EXTRA_SKIP = ("gov.uk", "wikipedia", "youtube.com", "instagram.com", "twitter.com", "x.com", "tiktok.com",
              "pinterest.", "trustpilot.", "yelp.", "tripadvisor.", "checkatrade.", "bark.com", "cylex",
              "scoot.co.uk", "freeindex", "thomsonlocal", "ukbizdb", "companieslist", "find-open")


def domain_label(host: str) -> str:
    """'www.lgmproducts.com' -> 'lgmproducts'; 'shop.example.co.uk' -> 'example'."""
    h = host.lower().removeprefix("www.")
    parts = h.split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "org", "ltd", "plc", "me", "net", "ac", "gov"):
        return parts[-3]
    return parts[-2] if len(parts) >= 2 else h


def name_tokens(name: str) -> list[str]:
    return [t for t in V.name_core(name).split() if t not in GENERIC and len(t) > 1]


def similarity(name: str, host: str) -> float:
    """Share of significant name tokens found in the domain label; initials count as a full match."""
    label = re.sub(r"[^a-z0-9]", "", domain_label(host))
    toks = [t.lower() for t in name_tokens(name)]
    if not toks or not label:
        return 0.0
    hits = sum(1 for t in toks if t in label)
    score = hits / len(toks)
    initials = "".join(t[0] for t in toks)
    if len(initials) >= 2 and label.startswith(initials):
        score = max(score, 0.75)
    joined = "".join(toks)
    if len(label) >= 4 and label in joined:
        score = max(score, 0.8)
    if _built_from_words_and_initials(label, toks):
        score = max(score, 0.8)   # e.g. autofixarc = AUTOFIX + Accident Repair Centre
    return round(score, 2)


def _built_from_words_and_initials(label: str, toks: list[str]) -> bool:
    """True if the label is exactly a sequence of whole name words and/or their initials (in order),
    using at least one whole word."""
    pos, whole = 0, 0
    for t in toks:
        if label.startswith(t, pos):
            pos += len(t)
            whole += 1
        elif pos < len(label) and label[pos] == t[0]:
            pos += 1
    return pos == len(label) and whole >= 1 and len(label) >= 4


def is_directory(host: str) -> bool:
    h = host.lower()
    return any(d in h for d in DIRECTORY_DOMAINS) or any(d in h for d in EXTRA_SKIP)


def best_domain(name: str, results, threshold: float = 0.5):
    scored = []
    for r in results:
        host = urlparse(r.url).netloc.lower()
        if not host or is_directory(host):
            continue
        scored.append((similarity(name, host), r.rank, host, r.url))
    scored.sort(key=lambda x: (-x[0], x[1]))
    if scored and scored[0][0] >= threshold:
        return scored[0], scored[1:4]
    return None, scored[:3]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", required=True)
    ap.add_argument("--out", default="domains.csv")
    ap.add_argument("--skip-dormant", action="store_true", help="Don't spend queries on dormant companies")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args(argv)

    backend = BraveBackend()
    rows = list(csv.DictReader(open(a.sample, newline="", encoding="utf-8-sig")))
    if a.limit:
        rows = rows[: a.limit]
    fields = ["company_number", "company_name", "domain", "score", "query", "url", "alternatives"]
    found = 0
    with open(a.out, "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=fields)
        w.writeheader()
        for i, r in enumerate(rows, 1):
            name, num = r["CompanyName"].strip(), V.normalise_company_number(r["CompanyNumber"])
            if a.skip_dormant and size_band(r.get("Accounts.AccountCategory", "")) == "dormant":
                continue
            core = V.name_core(name).title()
            town = (r.get("RegAddress.PostTown") or "").strip().title()
            q = f'"{core}" {town}'.strip()
            results = backend.search(q)
            best, alts = best_domain(name, results, a.threshold)
            alt_txt = "; ".join(f"{h} ({s})" for s, _, h, _ in alts)
            if best:
                found += 1
                s, _, host, url = best
                w.writerow(dict(company_number=num, company_name=name, domain=host, score=s, query=q,
                                url=url, alternatives=alt_txt))
            else:
                w.writerow(dict(company_number=num, company_name=name, domain="", score="", query=q,
                                url="", alternatives=alt_txt))
            fo.flush()
            print(f"[{i}/{len(rows)}] {name[:40]:40} -> {best[2] if best else '(none)'}")
    print(f"\nDomains found: {found}; Brave queries used: {backend.queries}. Saved {a.out}")
    print("Review the file: delete wrong domains, add ones you know. Empty domain = website route skipped.")


if __name__ == "__main__":
    main()

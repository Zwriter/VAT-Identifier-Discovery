"""
Route 3: number-keyed web search, snippet first.

Query ladder per company (stop at the first accepted hit). Snippets are judged directly;
the document is fetched only if the snippet lacks an anchor or joins fragments with '...'.

Backends are pluggable:
  - ManualBackend: results you saved by hand in a CSV (query, rank, url, title, snippet).
    Fine for a small research sample; never scrape a search engine's results page.
  - BraveBackend: Brave Search API (needs BRAVE_API_KEY). Check its terms and pricing.
The engine must honour exact phrases on numbers (one tested engine ignored "03574049").
"""
from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests

from ..core import vat as V
from ..core.attribute import Decision, Target, best, judge
from ..config import env_float, env_int, load_env
from ..web.fetch import Fetcher

# Directory / aggregator domains: useful for leads, never treated as the company's own site.
DIRECTORY_DOMAINS = (
    "company-information.service.gov.uk", "companieshouse.gov.uk", "opencorporates.com", "endole.co.uk",
    "companycheck.co.uk", "bizdb.co.uk", "yell.com", "linkedin.com", "facebook.com", "indeed.com",
    "glassdoor", "samatalent.com", "studysmarter", "192.com", "checkcompany.co.uk", "dnb.com",
    "zoominfo.com", "thegazette.co.uk", "find-tender.service.gov.uk", "contractsfinder.service.gov.uk",
    "google.", "bing.com", "wikipedia.org", "amazon.", "ebay.",
)


@dataclass
class Result:
    query: str
    rank: int
    url: str
    title: str
    snippet: str


@dataclass
class SearchOutcome:
    decision: Decision | None = None
    source_url: str = ""
    query: str = ""
    via: str = ""                     # snippet | document
    queries_run: int = 0
    candidate_domains: list[str] = field(default_factory=list)
    rejected: list[Decision] = field(default_factory=list)


def build_queries(t: Target) -> list[str]:
    n = V.normalise_company_number(t.company_number)
    variants = V.company_number_variants(n)
    padded, short = variants[0], variants[-1]
    region = ("Registered in Scotland" if n.startswith("SC") else
              "Registered in Northern Ireland" if n.startswith("NI") else "Registered in England")
    name = re.sub(r"\s+", " ", t.name).strip()
    # Letterhead wording finds documents; a bare "VAT" mostly finds directory/filing pages
    # (tested: "09351572" VAT returned annual returns, the letterhead query found the planning document).
    q = [f'"{padded}" "VAT Reg"']
    if short != padded:
        q.append(f'"{short}" "VAT Reg"')
    q.append(f'"{region}" "{short}" VAT')
    q.append(f'"{name}" "VAT Reg"')
    if t.postcode:
        q.append(f'"{name}" "{t.postcode}" VAT')
    q.append(f'"{name}" EORI')
    return q


class ManualBackend:
    """Reads results you collected by hand: CSV with columns query,rank,url,title,snippet."""
    def __init__(self, csv_path: str):
        self.by_query: dict[str, list[Result]] = {}
        with open(csv_path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                self.by_query.setdefault(r["query"].strip(), []).append(
                    Result(r["query"], int(r.get("rank") or 0), r["url"], r.get("title", ""), r.get("snippet", "")))

    def search(self, query: str) -> list[Result]:
        return sorted(self.by_query.get(query.strip(), []), key=lambda r: r.rank)


class BraveBackend:
    URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str | None = None, count: int = 10, min_interval: float | None = None,
                 max_queries: int | None = None):
        load_env()
        self.key = api_key or os.environ.get("BRAVE_API_KEY", "")
        if not self.key:
            raise RuntimeError("Set BRAVE_API_KEY in .env (see .env.example) or in the environment")
        self.count = count
        self.min_interval = min_interval if min_interval is not None else env_float("BRAVE_MIN_INTERVAL", 1.1)
        self.max_queries = max_queries if max_queries is not None else env_int("BRAVE_MAX_QUERIES", 900)
        self.queries = 0          # stays under the ~1,000/month covered by the free $5 credit
        self._last = 0.0

    def search(self, query: str) -> list[Result]:
        if self.queries >= self.max_queries:
            raise RuntimeError(f"Query budget reached ({self.max_queries}); raise max_queries deliberately")
        import time
        wait = self.min_interval - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)       # respect the per-second rate limit
        self._last = time.time()
        self.queries += 1
        r = requests.get(self.URL, params={"q": query, "count": self.count},
                         headers={"X-Subscription-Token": self.key, "Accept": "application/json"}, timeout=20)
        r.raise_for_status()
        out = []
        for i, item in enumerate(r.json().get("web", {}).get("results", []), 1):
            snippet = " ... ".join([item.get("description", "")] + item.get("extra_snippets", []))
            out.append(Result(query, i, item.get("url", ""), item.get("title", ""), re.sub(r"<[^>]+>", "", snippet)))
        return out


def _stitched_between(text: str, d: Decision, target: Target) -> bool:
    """True if '...' separates the VAT number from the company's number in the snippet."""
    hits = V.find_company_number(text, target.company_number)
    if not hits:
        return True
    near = min(hits, key=lambda p: abs(p - d.position))
    a, b = sorted((near, d.position))
    return "..." in text[a:b] or "…" in text[a:b]


def run_search(backend, f: Fetcher | None, target: Target, max_queries: int = 6) -> SearchOutcome:
    out = SearchOutcome()
    for q in build_queries(target)[:max_queries]:
        results = backend.search(q)
        out.queries_run += 1
        for r in results:
            host = urlparse(r.url).netloc.lower()
            if host and not any(d in host for d in DIRECTORY_DOMAINS):
                out.candidate_domains.append(host)
            text = f"{r.title} ... {r.snippet}"
            decisions = judge(text, target)
            d = best(decisions)
            if d and not _stitched_between(text, d, target):
                out.decision, out.source_url, out.query, out.via = d, r.url, q, "snippet"
                return out
            # snippet has a VAT number but no clean anchor -> open the document
            if decisions and f is not None:
                page = f.get(r.url)
                if page.text:
                    pd = best(judge(page.text, target))
                    if pd:
                        out.decision, out.source_url, out.query, out.via = pd, page.url, q, "document"
                        return out
            out.rejected += [x for x in decisions if not x.accepted]
    out.candidate_domains = list(dict.fromkeys(out.candidate_domains))
    return out

"""
Route 2: the company's own website, plus documents it links to.

robots.txt -> sitemap -> pick likely pages (contact, about, terms, privacy, legal + home)
-> follow same-site PDF links that look like documents (declarations, datasheets, terms)
-> extract text -> judge every GB VAT candidate against the target company.

Fail fast: at most MAX_PAGES pages and MAX_PDFS PDFs per company.
Observed: LGM Products had its VAT in the footer, the contact page and linked
Declaration of Performance PDFs; Autofix had a 5-page template site with nothing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from .attribute import Decision, Target, best, judge
from .fetch import Fetcher

MAX_PAGES = 10
MAX_PDFS = 5
MAX_SITEMAPS = 3

PAGE_WORDS = ("contact", "about", "terms", "condition", "privacy", "legal", "imprint", "company",
              "delivery", "returns", "policy", "who-we-are", "find-us")
PDF_WORDS = ("declaration", "dop", "datasheet", "data-sheet", "terms", "condition", "brochure",
             "price", "spec", "certificate", "catalogue", "catalog", "credit", "account")
SITEMAP_PATHS = ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml", "/page-sitemap.xml")


@dataclass
class SiteResult:
    domain: str
    decision: Decision | None = None
    source_url: str = ""
    reason: str = ""              # found | no_sitemap_no_home | site_no_vat | company_number_only | vat_no_anchor | blocked
    pages: list[str] = field(default_factory=list)
    rejected: list[Decision] = field(default_factory=list)


def _same_site(url: str, domain: str) -> bool:
    host = urlparse(url).netloc.lower()
    d = domain.lower().removeprefix("www.")
    return host == d or host.endswith("." + d)


def _score(url: str, words) -> int:
    u = url.lower()
    return sum(w in u for w in words)


def _sitemap_urls(f: Fetcher, base: str) -> list[str]:
    candidates = list(dict.fromkeys(f.robots_sitemaps(base) + [base + p for p in SITEMAP_PATHS]))
    locs: list[str] = []
    tried = 0
    queue = candidates[:]
    while queue and tried < MAX_SITEMAPS + len(SITEMAP_PATHS):
        sm = queue.pop(0)
        tried += 1
        page = f.get(sm)
        if page.kind not in ("xml", "html") or "<loc" not in page.text:
            continue
        found = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", page.text)
        nested = [u for u in found if u.lower().endswith(".xml")]
        locs += [u for u in found if not u.lower().endswith(".xml")]
        queue = nested[:MAX_SITEMAPS] + queue
        if locs and not nested:
            break
    return list(dict.fromkeys(locs))


def crawl_site(f: Fetcher, domain: str, target: Target) -> SiteResult:
    scheme = "http" if domain.startswith("http://") else "https"
    domain = re.sub(r"^https?://", "", domain).strip("/").split("/")[0]
    base = f"{scheme}://{domain}"
    res = SiteResult(domain)

    home = f.get(base + "/")
    if home.kind == "error" and home.error == "robots_disallow":
        res.reason = "blocked"
        return res
    locs = _sitemap_urls(f, base)
    links = home.links if home.kind == "html" else []
    pool = [u for u in dict.fromkeys(locs + links) if _same_site(u, domain)]

    pages = [u for u in pool if not u.lower().endswith(".pdf")]
    pages = sorted(pages, key=lambda u: -_score(u, PAGE_WORDS))
    keyword_pages = [u for u in pages if _score(u, PAGE_WORDS) > 0]
    other_pages = [u for u in pages if _score(u, PAGE_WORDS) == 0 and u.rstrip("/") != base]
    # keyword pages first; leftover budget goes to other pages (product pages often link the PDFs)
    chosen = (keyword_pages + other_pages)[: MAX_PAGES - 1]
    pdfs = [u for u in pool if u.lower().endswith(".pdf")]

    texts: list[tuple[str, str]] = []
    if home.kind == "html":
        texts.append((home.url, home.text))
        res.pages.append(home.url)
    elif not locs:
        res.reason = "no_sitemap_no_home"
        return res

    for u in chosen:
        p = f.get(u)
        res.pages.append(u)
        if p.kind == "html":
            texts.append((p.url, p.text))
            pdfs += [l for l in p.links if l.lower().endswith(".pdf") and _same_site(l, domain)]

    pdfs = sorted(dict.fromkeys(pdfs), key=lambda u: -_score(u, PDF_WORDS))
    for u in [u for u in pdfs if _score(u, PDF_WORDS) > 0][:MAX_PDFS]:
        p = f.get(u)
        res.pages.append(u)
        if p.kind == "pdf" and p.text:
            texts.append((p.url, p.text))

    # Own site: footer numbers repeated on every page are the company's own -> no template filter.
    any_number_seen = False
    for url, text in texts:
        decisions = judge(text, target)
        d = best(decisions)
        if d:
            res.decision, res.source_url, res.reason = d, url, "found"
            return res
        res.rejected += [x for x in decisions if not x.accepted]
        if not any_number_seen and _mentions_company_number(text, target):
            any_number_seen = True

    if res.rejected:
        res.reason = "vat_no_anchor"
    elif any_number_seen:
        res.reason = "company_number_only"
    else:
        res.reason = "site_no_vat"
    return res


def _mentions_company_number(text: str, target: Target) -> bool:
    from .vat import find_company_number
    return bool(find_company_number(text, target.company_number))

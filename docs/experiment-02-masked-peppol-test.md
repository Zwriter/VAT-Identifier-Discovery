# Experiment 02 — Masked Peppol test: can the crawler rediscover known VAT numbers?

Related: [REPORT.md](../REPORT.md) · [Experiment 01](experiment-01-blind-manual-search.md) · [Experiment 02](experiment-02-masked-peppol-test.md) · [crawler](../crawler/README.md)

## Key points

- **The website route found 0 of 40 VAT numbers** (95% CI 0–9%) for companies that are *known* to be VAT-registered (they are in Peppol under their VAT number).
- **It attached 0 wrong numbers.** The strict acceptance rules produced no false positives — the error the brief calls the most expensive.
- **Not a bug — verified by hand.** Thorcal's site shows `Company No: 12172366` but no VAT number; Nettex.io shows only "All prices exclude VAT". The crawler fetched the pages fine (242/255 requests OK).
- **Small UK companies don't publish their VAT number on their own website**, even when registered and using e-invoicing: of 23 sites crawled, 8 showed the company number, **none** showed a VAT number, and none linked a PDF document.
- **Domain discovery is the first bottleneck:** no own website found for 17/40 (43%).
- **New signal found:** sites that say "prices exclude VAT" / "+ VAT" prove registration without showing the number → added to the crawler (outcome `registered_not_found`), plus the opposite ("not VAT registered").
- **Implication:** the numbers live in **registries (Peppol)** and **third-party documents** (letterheads on resellers' and councils' sites), not on the companies' own sites. Crawling budget should go there.

---

## 1. Setup

| | |
|---|---|
| Date | 2026-11-25 |
| Truth source | Peppol UK extract: GB VAT numbers as participant IDs (scheme 9932) |
| Link to Companies House | Normalised-name match, **unique matches only**: **17,486 of 22,541** Peppol UK VAT numbers (78%) match exactly one active company (33 ambiguous names excluded) |
| Test set | 40 random companies (seed 7), dormant excluded → **22 small, 17 micro, 1 no-accounts-yet, 0 medium/large** |
| Masking | Crawler input `peppol_test_sample.csv` has no VAT numbers; answers kept in `peppol_test_truth.csv` |
| Routes run | Website only (Peppol and search off, to measure the crawler alone) |
| Domains | Brave Search API, query `"<name>" <post town>`, directories skipped, name-similarity ≥ 0.5 — **40 queries** |
| Crawl budget | ≤10 pages + ≤5 PDFs per site, robots.txt respected, 1 req/s per host |

Commands: see `crawler/README.md` → "Masked-Peppol test".

## 2. Results

### Headline
| Metric | Value |
|---|---|
| Recall (correct VAT found) | **0/40 = 0%** (95% CI 0–9%) |
| Numbers attached | 0 → precision / wrong-number rate n/a |
| **Wrong numbers attached** | **0** |
| Not found | 40/40 |

### Why not found
| Reason | Companies | Meaning |
|---|---|---|
| No own website found | 17 | Brave returned only directories / unrelated sites (doogal, police-uk, companies-in-the-uk …) |
| `site_no_vat` | 15 | Site crawled; neither VAT number nor company number on the pages fetched |
| `company_number_only` | 8 | Site shows the company number (legal requirement) but **not** the VAT number |

By size band: small 0/22, micro 0/17, no-accounts-yet 0/1.

### Crawl cost
- **255 HTTP requests** for 23 sites (≈11 per site): 242 OK, 10 × 404, 3 connection errors.
- **0 PDFs** found via same-site links (documents simply weren't linked).
- 40 Brave queries for domain discovery.

## 3. Verifying it isn't a bug

| Check | Result |
|---|---|
| Request log | 242/255 OK; pages returned real HTML (148+ text/html responses) |
| **Thorcal Ltd** home page (browser) | Footer: "© 2026 Thorcal Ltd. Company No: 12172366." — **no VAT number** |
| **Nettex.io** home page (browser) | "All prices exclude VAT." — **no VAT number** (registration evidence only) |
| Thin pages | Hooga Group (5 tiny pages), August Twenty (5), Exede (3) → JavaScript-built sites; the crawler sees almost no text → **known blind spot** |

## 4. Domain-discovery problems found

| Company | Domain picked | Issue |
|---|---|---|
| Meadgate Pool Ltd | meadgateprimary.com | **Wrong** (a primary school); scored exactly 0.5 on "MEADGATE" |
| Romsey Ltd | romseygolfclub.com | Uncertain (could genuinely be the golf club's company) |
| Actus Construction Ltd | actusinteriors.com | Plausible but unconfirmed |
| D A Utility Services Ltd | *(none)* | **Missed** daus.co.uk — single-letter initials were dropped → **fixed** (all-word initials now match) |
| Nettex Technology Ltd | nettex.io | Alternative nettex.co.uk also scored 0.8 → two candidate domains |

Mitigation added: website evidence is only used when the **site identity is confirmed** (company name or number appears on it), so a wrong domain can't produce evidence.

Lead spotted: **vat-lookup.co.uk** appeared in Decorous Ltd's results — a third-party VAT lookup directory. To check: where its numbers come from, coverage, and terms (debate topic 4).

## 5. Conclusions

1. **The website route has a very low ceiling for small companies.** Measured on companies certain to be registered: 0/40, CI upper bound 9%. Combined with Experiment 01 (Autofix: nothing on its site), the own-website route is not where VAT numbers are for the long tail.
2. **Strict attribution works:** 0 false positives. Precision is safe; the problem is recall.
3. **Domain discovery fails for 43%** of small companies (no own site found), and needs review for the rest.
4. **The useful by-product is registration evidence:** pricing phrases ("ex VAT", "+ VAT") separate "registered, number not found" from "not registered" automatically.
5. **Bias:** Peppol companies are e-invoicing adopters (more digital, B2B). If *they* don't show VAT numbers on their sites, the wider long tail is unlikely to do better.

## 6. Changes made to the crawler after this test

- `signals.py`: detects "prices exclude VAT", "£X + VAT", "ex/excl VAT", "VAT registered", "VAT invoice" → `registered_not_found (site_mentions_vat_pricing)`; "not VAT registered", "no VAT charged", "below the VAT threshold" → `probably_not_registered (site_says_not_vat_registered)`. Explicit "not registered" wins.
- Site identity check (`site_identity` column): evidence only from sites that name the company.
- `peppol_test evaluate` now reports registration evidence on not-found companies (all truth companies *are* registered, so any "not registered" verdict there measures the detector's error).
- Domain finder: all-word initials ("daus" = D A Utility Services).
- 31 tests pass.

**Next:** fix wrong domains in `peppol_test_domains.csv`, rerun → measure how many of the 40 get `registered_not_found` (expected > 0, e.g. Nettex).

## 7. Other discoveries this session

| Finding | Evidence |
|---|---|
| **Population denominator:** 5,176,384 active companies vs ~2.18M VAT registrations (incl. sole traders) → **at most ~42%** of active companies can be registered | `ch_slim_meta.json` (full Companies House file, 2026-11-01) |
| Size bands (active): micro 1.69M (33%), small 1.48M (29%), no accounts yet 1.34M (26%), dormant 0.56M (11%), medium/large 0.11M (2%) | same |
| **Peppol in the random sample: 0/50** (95% CI 0–7%) — consistent with ~1% coverage | `results_peppol_only.csv` |
| **Peppol → Companies House linkage: 78%** unique name matches (17,486/22,541) | `peppol_test` build |
| Peppol's UK base is overwhelmingly small/micro (test draw: 0 medium/large of 40) | `peppol_test_truth_meta.json` |
| **Google's search API closed to new customers** (ends 2027-01-01); **Bing's API retired** (2025-08-11) | public announcements |
| **Brave failed the exact-number test:** `"3574049" VAT` didn't return the LGM letter and drifted to unrelated numbers; `site:`/`filetype:` ignored | manual test |
| **DuckDuckGo (≈ Bing index) found 3 LGM letters, 2 not on Google's first page**; found nothing for Dale; returned annual-return pages for Sammons | manual test |
| Bare `"<number>" VAT` finds directory/filing pages; **letterhead wording** (`"<number>" "VAT Reg"`) finds documents → query ladder changed | Sammons case |
| **Structural risk:** number-keyed search depends on Google's index, which has no API for new developers | above |

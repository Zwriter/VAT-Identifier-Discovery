# VAT Identifier Discovery — crawler

Proof of concept for the Veridion *VAT Identifier Discovery* challenge: for a random sample of UK
companies, try to find each company's VAT number from open sources, attach it only when the
evidence ties it to that company, and record why it failed when it didn't.

Design notes: `PKM/VAT Identifier Discovery - Crawler Design.md`.

**Data setup is required first** (Companies House file, Peppol export): see the main [README](../README.md#data-setup-required--not-included-in-this-repository).
Peppol tools live in [`scripts/`](scripts/): `peppol_preview.py` (inspect) and `peppol_uk_fast.py` (UK extract → `data/peppol_uk.csv`).

## Routes (cheapest first, stop at the first accepted candidate)

| # | Route | Needs | What it does |
|---|---|---|---|
| 1 | Peppol | `peppol_uk.csv` | Name lookup in the UK Peppol extract (GB VAT = scheme 9932) |
| 2 | Website | `domains.csv` (or a domain found by route 3) | robots.txt → sitemap → contact/about/terms/legal pages + other pages up to a budget → same-site PDFs (declarations, datasheets, terms) |
| 3 | Search | `--search-csv` (manual) or `--search brave` | Query ladder keyed on the company number (padded and unpadded), letterhead wording, name + postcode, EORI. Snippet first; the document is opened only if needed |
| 4 | Registration evidence | manual | Accounts (reserves growth > £90k → must be registered), job ads mentioning VAT returns |

## Acceptance (all must hold)

1. `GB` + 9 digits (or 12-digit branch / GBGD / GBHA) after removing spaces and dots.
   EORI `GB` + VAT + `000` is mapped back to the VAT number; other EORI suffixes are not guessed.
2. mod-97 checksum (both series).
3. Within 300 characters of the target's **company number** (padded or unpadded) **or** its
   **postcode district + name**. Non-GB numbers (e.g. a directory's own `VAT IE ...` footer) never match.
4. If two different numbers are accepted on one page → ambiguous → rejected.
5. **HMRC confirms** (valid + name matches Companies House). Until then a row is `found_unverified`
   and is not reported as found.

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
# 0. Shrink the Companies House file once (only useful columns + derived fields; chunked, low memory)
python -m vatcrawl.slim_ch --ch ../unseen_data/BasicCompanyDataAsOneFile-2026-11-01.csv \
    --out ../data/ch_slim.csv --active-only --drop-other-band

# 1. Draw a frozen, stratified random sample from the slim file
python -m vatcrawl.sample --ch ../data/ch_slim.csv --per-band 10 --seed 42 --out ../data/sample.csv

# 2. (optional) domains.csv: company_number,domain  for companies whose website you know
# 3. (optional) manual_search.csv: query,rank,url,title,snippet  (results you collected by hand;
#    queries are printed by: python -c "from vatcrawl.search import build_queries; ...")

# 4. Run the routes
python -m vatcrawl.pipeline --sample sample.csv --peppol ../peppol_uk.csv \
    --domains domains.csv --search-csv manual_search.csv --out results.csv --log crawl_log.jsonl

# 5. Verify every found_unverified row on https://www.gov.uk/check-uk-vat-number
#    and fill hmrc_status (valid | not_found), hmrc_name, hmrc_postcode in results.csv.
#    For 'unknown' rows, add registration_evidence where you have it.

# 6. Final outcomes + Part 2 tables (per band, per route, false-positive rates with 95% CI)
python -m vatcrawl.report --results results.csv --out results_final.csv
```

Registration evidence from a website is only used when the site is confirmed to be the company's
(its name or company number appears on it), so a wrongly matched domain can't produce evidence.
Every result also carries `registration_prior` (from Companies House size band / charges), and
`report.py` splits "not found" into likely discovery failures vs unlikely-registered companies.

## Masked-Peppol test

```bash
python -m vatcrawl.peppol_test build --peppol ../data/peppol_uk.csv --ch ../data/ch_slim.csv --n 40 --seed 7 \
    --exclude-dormant --out-sample ../data/peppol_test_sample.csv --out-truth ../data/peppol_test_truth.csv
python -m vatcrawl.find_domains --sample ../data/peppol_test_sample.csv --out ../data/peppol_test_domains.csv
python -m vatcrawl.pipeline --sample ../data/peppol_test_sample.csv --domains ../data/peppol_test_domains.csv \
    --routes website --out ../data/peppol_test_results.csv --log ../data/peppol_test_log.jsonl
python -m vatcrawl.peppol_test evaluate --results ../data/peppol_test_results.csv --truth ../data/peppol_test_truth.csv
```

## Outputs

- `results.csv` — one row per company: outcome, reason code, VAT, route, evidence type,
  source URL, ±150-char context, rejected candidates, requests/bytes/seconds (cost per company).
- `crawl_log.jsonl` — every HTTP request (URL, status, bytes, time, company) → traceable trail.

## Outcomes

| Outcome | Meaning |
|---|---|
| `found_verified` | HMRC valid and name matches |
| `found_wrong_company` / `found_invalid` | false positives (reported, never hidden) |
| `registered_not_found` | evidence of registration, number not found — automatic when the company's own site says e.g. "prices exclude VAT" / "+ VAT" (`site_mentions_vat_pricing`), or added by hand |
| `probably_not_registered` | dormant / strike-off, or the site says "not VAT registered" (`site_says_not_vat_registered`) |
| `unknown` | reason code: `no_website_found`, `site_no_vat`, `company_number_only`, `vat_no_anchor`, `blocked` |

## Politeness and limits

- Respects robots.txt; 1 request/second per host (`--delay`); identifies itself in the User-Agent.
- At most 10 pages and 5 PDFs per site; files over 5 MB are truncated; no OCR (scanned PDFs are missed).
- Never scrapes a search engine's results page: search uses hand-collected results or an official API.
- Stores only company fields; personal names/signatures in documents are not extracted.

## Tests

```bash
python -m pytest -q tests
```

31 tests, built from real cases met during research (LGM Products letterhead + EORI, Dale Techniche
footer with "No .4955915", Sammons Architectural planning-portal snippet, a directory page showing its
own Irish VAT number, the "APM (SALES & SERVICE) UK" false match, Autofix in Peppol), plus an offline
end-to-end run against local fake sites.

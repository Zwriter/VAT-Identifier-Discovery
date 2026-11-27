# Experiment 03 - Common Crawl: VAT numbers at web scale

Related: [REPORT.md](../REPORT.md) · [Experiment 01](experiment-01-blind-manual-search.md) · [Experiment 02](experiment-02-masked-peppol-test.md) · [crawler](../crawler/README.md)

## Key points

- **Best source found.** A random 0.05% of the November 2026 Common Crawl (50 of 100,000 files, 1,079,230 web pages) gave **1,196 distinct VAT numbers tied to active UK companies** through the company number printed next to them.
- **Almost all of them are new.** Only 44 of the 1,196 are in Peppol, the e-invoicing registry that was the best source until now.
- **The pairs are clean.** 81% of pages that show a valid VAT number also show a labelled company number, usually within a few words (median 23 characters). 95% of those company numbers belong to active companies.
- **HMRC confirms them.** 20 random pairs checked by hand: 20/20 valid, 0 attached to the wrong company. In 2 cases HMRC shows the parent group's name, because the company is part of a VAT group.
- **It reaches small companies.** 57% small, 21% medium/large, 19% micro. Large companies are over-represented (they are 2% of all companies), but micro companies still make up almost a fifth.
- **Cost of the experiment: nothing but time.** Files were streamed and discarded; disk use stayed near zero on a laptop.

## 1. Why try it

The company-website crawler (Experiment 02) found 2 VAT numbers for 80 companies. Most of the failures happened before extraction: no website found, or the wrong website. Common Crawl removes that problem. It is a free, public copy of about 2.2 billion web pages, recrawled every month. Instead of asking "where is this company's VAT number?", the question becomes "which VAT numbers are on the web at all, and whose are they?"

A second reason: UK companies must show their registered company number on their website (the Companies (Trading Disclosures) Regulations 2008). So if a site shows a VAT number, the company number is probably on the same page, and the company number is what makes a VAT number attributable.

## 2. Setup

- **Data:** Common Crawl CC-MAIN-2026-47 (November 2026). I used the WET files, which contain only the plain text of each page. There are 100,000 of them, about 60 MB each compressed (6 TiB in total).
- **Sample:** 50 files chosen at random (seed 1). Each file is a random slice of the crawl, so counts scale by roughly 2,000 to the full crawl.
- **Method** (`crawler/scripts/scan_common_crawl.py`):
  1. Stream each file, decompress it on the fly, never save it.
  2. On each page, find valid GB VAT numbers with the same rules as the crawler: GB prefix or a "VAT" label, plus the HMRC checksum.
  3. Look for a *labelled* company number ("Company No", "Registered in England No", "Company Registration No") within 300 characters of the VAT number. Digits that are part of the VAT number itself are not counted.
  4. Join each company number to the Companies House file of 5.18M active companies, and add the company's name and postcode.
  5. Pick 20 random pairs and check them by hand on HMRC's "Check a UK VAT number" service.
- **Run time:** under 10 minutes for 50 files on a home connection.

## 3. Results

| | Count |
|---|---|
| Pages scanned | 1,079,230 |
| Pages on .uk domains | 23,507 |
| Pages with a valid GB VAT number | 2,058 |
| ...of which also show a labelled company number nearby | 1,674 (81%) |
| Distinct (VAT number, company number) pairs | 1,269 |
| Pairs whose company number is an active company | 1,206 (95%) |
| Distinct VAT numbers in those pairs | 1,196 |
| Of those, already in Peppol | 44 (4%) |
| VAT numbers paired with more than one company | 8 |

**Size of the companies found** (from Companies House accounts category):

| Band | Share of finds | Share of all active companies |
|---|---|---|
| Small | 57% | 29% |
| Medium / large | 21% | 2% |
| Micro | 19% | 33% |
| No accounts yet | 3% | 26% |
| Dormant | 0.4% | 11% |

**Hosts:** 1,321 different websites. No single site contributed more than 4 VAT numbers, so the result is not driven by one directory. 87% of pair rows come from .uk domains.

**Example pairs** (as they appear on the page):
- "Company registered in England and Wales. Registered Number: 8924632. VAT Number: 591 0298 34." (Switalskis Solicitors)
- "Company Registration No. 2904363. VAT no. GB 636 8152 26" (Hills Retail Stores)
- "Rose & Rose Solicitors LLP (Company no. OC363353) VAT Number: GB 928 5154 08"

## 4. HMRC check (20 random pairs)

| Result | Count |
|---|---|
| Valid at HMRC | 20 / 20 |
| HMRC name matches the company exactly (ignoring Ltd vs Limited) | 18 / 20 |
| HMRC name is the parent group | 2 / 20 (Primer Design -> Novacyt UK Holdings; Harrison Leisure UK -> Harrison Leisure Group) |
| Attached to the wrong company | 0 / 20 |

95% confidence interval for both the invalid rate and the wrong-company rate: 0-16%. A larger audit would narrow this.

One case was written as GB442803606000 (Jag Couture). The trailing 000 is the EORI customs-number format, and the first 9 digits were the VAT number, which HMRC confirmed.

## 5. VAT groups: one number, several companies

8 VAT numbers appeared next to more than one company number. Looking at them, most are VAT groups: related companies that register together under one VAT number. Examples: Clarion Events (company numbers 00454825 and 00454826), the Sykes Cottages companies, The Growth Company companies. This is legal and common for groups, and HMRC shows the group's representative company, which explains the 2 name differences above.

Consequence for the dataset: one VAT number can belong to several companies. The data model has to allow that, otherwise correct numbers look like errors.

## 6. How big is the full crawl?

- **Upper bound:** 1,206 pairs x 2,000 = about 2.4 million. This overcounts, because a big company's footer appears on many pages and turns up in several files.
- **Evidence it is far from the limit:** new VAT numbers kept appearing at a steady ~24 per file (284 after 10 files, 538 after 20, 767 after 30, 976 after 40, 1,197 after 50). Only 182 of 1,258 VAT numbers appeared in more than one file.
- **Lower bound:** a standard estimator for "how many have we not seen yet" (Chao2) gives about 5,400, but it is known to underestimate badly when only 0.05% has been sampled.
- **Honest summary:** somewhere between thousands and low millions; scanning a few hundred more files would show whether the curve starts to flatten.

## 7. Conclusions

1. **The open web does contain UK company VAT numbers at scale, attached to a company number.** The problem was looking for them company by company.
2. **A crawl-wide scan beats a per-company crawl by orders of magnitude.** About 1,200 attributable numbers from 0.05% of the crawl, versus 2 numbers from 80 targeted companies.
3. **Precision looks high** (20/20), because the company number gives an exact join to Companies House, unlike name matching (7% wrong company in the Peppol test).
4. **The bias is toward companies with websites.** Micro companies are under-represented; companies without a website will not appear.
5. **Pages can be months old,** so every pair needs an HMRC check before it is stored.

## 8. Limitations

- 50 files and 20 HMRC checks: small samples, wide intervals.
- WET text only. PDF letterheads and text inside images are not covered.
- The company-number label pattern misses unlabelled numbers and some unusual wordings.
- Total size of the full-crawl yield is not yet known (section 6).

## 9. Files

- `crawler/scripts/scan_common_crawl.py`, scanner and `--summary` report; tests in `crawler/tests/test_common_crawl.py`
- `data/cc_pairs.csv`, every pair with page URL and text snippet
- `data/cc_vats.csv`, every valid VAT number seen, with or without a company number
- `data/cc_stats.json`, page counts and files scanned
- `data/cc_hmrc_check.csv`, the 20 pairs and the HMRC results

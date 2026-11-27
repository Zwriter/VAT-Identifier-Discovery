# Experiment 01 — Blind manual search for one VAT number

Related: [REPORT.md](../REPORT.md) · [Experiment 01](experiment-01-blind-manual-search.md) · [Experiment 02](experiment-02-masked-peppol-test.md) · [crawler](../crawler/README.md)

## Key points

- **The VAT number was not findable anywhere on the open web.** Companies House, search engines, the company's own website and a job ad all failed.
- **The only source with the number was the Peppol Directory**, and the company had joined it **less than a month earlier** (2026-10-27). Before that, it was undiscoverable.
- **Registration could be proven without the number**, two ways: a job ad listing VAT-return duties, and the company's own accounts (retained profit grew by £292k in a year → turnover far above the £90k threshold).
- **HMRC confirmed** GB359057474 → "AUTOFIX ACCIDENT REPAIR CENTRE", EH20 9QH (= Companies House postcode). Checked by me on gov.uk and in the browser session.
- **Implication:** for small local suppliers, a website crawler has a low ceiling. The common outcome will be **"registered, number not found"**, which is a discovery failure, not "not registered".

---

## 1. Setup

| | |
|---|---|
| Date | 2026-11-24, ~18:15–19:00 (≈45 min including discussion) |
| Company | **AUTOFIX ACCIDENT REPAIR CENTRE LTD** |
| Company number | **SC673813** (Scotland) |
| Registered office | EH20 9QH (Loanhead, Midlothian) |
| Accounts category | Unaudited abridged (small company) |
| Why this company | Drawn from my Peppol ↔ Companies House sample (row 23 of `hmrc_check_sample.csv`, seed 42), but **not one of the 17 already HMRC-checked**. The answer existed but I didn't know it → **blind test**. |
| Why it's representative | Small local business with a basic website — the profile of the customer's missing suppliers, not a big corporate. |
| Rule | Don't open the files containing the answer until all other routes are exhausted. |

## 2. Search log

| # | Route | What I did | What came back | Outcome |
|---|---|---|---|---|
| 1 | **Companies House filings** | Reviewed filing categories (accounts, capital, charges, confirmation statements, incorporation, officers) | No filing type has a VAT field | no number |
| 2 | **Latest accounts** (y/e 30 Sep 2025, PDF) | Read all 8 pages | Abridged; P&L not filed; no creditors breakdown; no VAT number. Reserves £302,940 → £595,357 (+£292,417); 13 employees; debtors £165,868 | no number · **registration proven by inference** (§3) |
| 3 | **Search engine operators** | Brave: `site:autofixarc.com filetype:pdf` | "Search operators were not applied — too few matches" | tool limitation (not evidence of absence) |
| 4 | **Company website — sitemap** | Opened `autofixarc.com/sitemap.xml` | 5 pages: home, contact, our-services, reviews, review-submission. Squarespace template. Last modified 2021. No terms, privacy, legal pages or PDFs | no number |
| 5 | **Company website — pages** | Checked pages for VAT / legal details | Nothing VAT-related | no number |
| 6 | **Web search** `"Autofix Accident Repair Centre" VAT` | Brave + its AI summary | No number. AI summary cited a job ad with VAT duties (its "registered in Scotland → subject to VAT" reasoning is wrong: company ≠ VAT registration) | no number · lead → #7 |
| 7 | **Job ad** (StudySmarter aggregator) | Opened the actual listing | Description: "Autofix Accident Repair Centre – Loanhead, EH20 9QH", "Preparing for VAT returns in line with HMRC requirements". Header wrongly says **Stevenage**. No company number, no date | no number · **registration evidence** (postcode = CH) |
| 8 | **Peppol Directory** (answer reveal) | Looked up in my Peppol UK extract | `9932:gb359057474`, name "AUTOFIX ACCIDENT REPAIR CENTRE", registered **2026-10-27** | **number found** |
| 9 | **HMRC checker** | gov.uk/check-uk-vat-number, `359057474` | **Valid** — "AUTOFIX ACCIDENT REPAIR CENTRE", 7 Borthwick View, Pentland Industrial Estate, Loanhead, Midlothian, **EH20 9QH**. Checked 24 Nov 2026, 4:58pm GMT | **verified** |

Job ad URL: https://talents.studysmarter.co.uk/companies/autofix-accident-repair-centre/stevenage/accounts-assistant-bookkeeper-37172259/ (accessed 2026-11-24)

## 3. Proving registration without the number

From the company's own accounts (route 2):

1. Profit and loss reserve rose from **£302,940 to £595,357** = **+£292,417** in one year.
2. Retained profit can't exceed turnover → turnover **≥ £292k** (realistically much higher: wages and parts come first).
3. £292k > **£90k** VAT threshold, and vehicle repair is standard-rated → **VAT registration is mandatory.**
4. Supporting: 13 employees, £166k trade debtors, £296k short-term creditors (likely includes VAT owed, but not broken down).

Assumption: no dividends hid profit. Dividends would make true profit *higher*, so the conclusion still holds.

**Generalisable signal:** year-on-year growth in retained profit gives a **lower bound on turnover**, even when the P&L isn't filed. Companies House publishes accounts as bulk machine-readable data (iXBRL), so this could flag likely-registered companies at scale. Not yet checked how consistently small-company filings tag these values.

## 4. Attribution evidence

| Evidence | Source | Strength |
|---|---|---|
| Postcode EH20 9QH | Companies House = job ad = Peppol (via HMRC) = HMRC | **Strong** |
| Name "AUTOFIX ACCIDENT REPAIR CENTRE" | HMRC and Peppol drop "LTD"; CH has "LTD" | Strong after normalisation |
| Company number SC673813 | Only in Companies House and the accounts — **not** on the website, job ad or Peppol | Absent where it would matter |

Notes:
- The VAT-registered name omits "LTD" → name matching must normalise legal suffixes.
- The job aggregator mislabelled the location (Stevenage vs Loanhead) → match on the strongest identifier (postcode in the description), never on a header/city field.
- The company number — the planned "strongest attribution anchor" — appeared on **none** of the web sources. For small suppliers it may often be absent.

## 5. Conclusions

1. **Outcome category:** *registered (proven) — number not discoverable on the open web — found in Peppol.*
2. **Website crawling has a low ceiling for this profile.** A 5-page template site with no legal pages, untouched since 2021, contains nothing to extract. Expect similar for many micro/small companies; measure it by size band.
3. **Peppol's value is growing and time-dependent.** This company joined 27 days before the test. Coverage measured today will be different in a year (≈500 new UK entries/month).
4. **"Not found" ≠ "not registered".** Here two independent public signals (job ad, accounts) prove registration. Without them, this company would wrongly look like "probably not registered".
5. **Small-but-real details matter:** the missing "LTD", the wrong city header, and Brave ignoring operators are each a concrete example for the write-up.

## 6. Implications for the crawler and the write-up

**Crawler design**
- Sitemap-first, fetch ≤ ~10 likely pages, stop early. Cheap fail-fast.
- Record **why** a company failed, not just "not found":
  `no website found` / `site found, no legal details` / `company number shown, no VAT` / `VAT found`.
- Results table with **four outcomes**: `VAT found + verified` / `registered, number not found (with evidence)` / `probably not registered` / `unknown`.
- Name normalisation: strip legal suffixes (Ltd/Limited) but **not** distinguishing words like "UK" (see the false match in the 17 HMRC checks).

**Write-up**
- Part 1: use this as the worked "I started here, tried this, it failed because…" example.
- Part 1/3: accounts-based registration inference as a non-obvious finding.
- Part 3: the customer's own invoice archive already contains supplier VAT numbers (the brief says the number is on the invoice) → OCR + checksum + HMRC could be the cheapest, most accurate source for their missing suppliers.
- Debate topic 2 (keeping current): Peppol growth; this company only became discoverable a month ago.
- Interview: a ready "path I abandoned" (company website / search operators) with the exact reason and evidence.

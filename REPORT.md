# Can a UK company VAT dataset be built from the open web?

Veridion - VAT Identifier Discovery (Data Assets Intern challenge)

## Summary

**Yes, for a large share of companies that have a website, and with high accuracy. No, for small companies that have no web presence.**

- **The best source is Common Crawl,** a free public copy of about 2.2 billion web pages. Scanning a random 0.05% of it found **1,196 VAT numbers tied to active UK companies** through the company number printed next to them. 96% of them appear in no other open source I found. 20 random ones checked on HMRC were all valid and none belonged to the wrong company.
- **The second source is Peppol,** the European e-invoicing network, where UK businesses are listed under their VAT number: 22,575 valid UK VAT numbers. It is very accurate, but it covers only about 1% of UK VAT registrations.
- **Looking company by company does not work.** A crawler that visited each company's own website found the VAT number for 2 of 80 companies known to have one. Most small companies' websites simply don't show it.
- **Public records are a dead end.** Council spending files (693,835 payments), government tender notices and the Gazette contained almost no UK VAT numbers.
- **For a customer missing VAT numbers for 27,000 suppliers,** the recommended route is: scan the full Common Crawl once, match the results to the suppliers by company number, add Peppol, confirm everything with HMRC, and collect the rest from the VAT numbers already printed on the suppliers' invoices.

### Terms used in this report

| Term | Meaning |
|---|---|
| VAT number | A UK business's tax registration number: GB followed by 9 digits, e.g. GB823841235 |
| Company number | The 8-character number every UK company gets from Companies House, e.g. 02904363 |
| Companies House | The UK register of companies. It publishes every company's name, number, address and size, but not VAT numbers |
| HMRC check | HMRC's free online service: enter a VAT number, get back whether it is valid and the business name and address |
| Checksum | A built-in arithmetic test in every VAT number. It catches typos, but a random 9-digit number still passes about 1 time in 97 |
| Attribution | Proving that a VAT number belongs to *this* company and not another one |
| False positive | A VAT number attached to the wrong company, or an invalid one |
| Peppol | A European e-invoicing network with a public directory of its members |
| Common Crawl | A non-profit that crawls the web every month and publishes the pages for free |

---

## Part 1 - Research

### 1.1 How I approached the problem

I split the problem into three steps, because each fails differently:

1. **Find** a VAT number that might belong to the company.
2. **Validate** it: the checksum, then the HMRC check.
3. **Attribute** it: prove it belongs to this company. This is the dangerous step. An invalid number is caught by HMRC; a valid number attached to the wrong company looks perfectly fine and quietly corrupts the data.

I also checked how many companies *can* have a VAT number. There are 5,176,384 active companies on Companies House (November 2026) and about 2.2 million VAT registrations, including sole traders who are not companies. So **at most about 42% of active companies are VAT-registered.** For a random company, "no VAT number found" is often the correct answer. That is why my results separate "not found" from "not registered".

### 1.2 What wasn't obvious at the start

- **The company number is the key to attribution.** UK companies must show their company number on their website and letterheads. When a VAT number sits next to a company number on a page, the match to Companies House is exact. Matching by company name alone attached the wrong company in about 1 case in 15.
- **The web holds the numbers, but not where you'd look first.** Small companies' own websites rarely show a VAT number, yet a crawl-wide scan found over a thousand numbers in a tiny slice of the web.
- **An e-invoicing directory is a ready-made VAT list.** UK members of Peppol are identified by their VAT number.
- **The customs (EORI) number contains the VAT number.** For VAT-registered businesses it is GB + VAT number + 000. I confirmed this on a real letterhead.
- **One VAT number can belong to several companies.** Groups of companies can register together for VAT. HMRC then shows the group's lead company, so a correct number can look like a mismatch.
- **Web search APIs have closed.** Google's search API is closed to new customers, Bing's was retired in August 2025, and the independent alternative (Brave) could not find exact numbers. Searching for one company at a time therefore has no reliable automated route.

### 1.3 Sources I tried

| Source | What I did | What I found | Useful? |
|---|---|---|---|
| **Common Crawl** | Scanned 50 random files out of 100,000 (1.08 million pages) | 1,196 VAT numbers next to an active company's number; 96% not in Peppol; 20/20 valid at HMRC, 0 wrong company | **Yes, the best source** |
| **Peppol directory** | Downloaded the full export (19.6 GB, 9.76 million entries) and extracted UK entries | 22,575 valid UK VAT numbers (about 1% of registrations); 78% matched one company by name | **Yes, accurate but small** |
| **Companies House** | Full company file (5.71 million rows) | No VAT numbers anywhere; used as the list of companies and for company size | Yes, as the backbone |
| **HMRC check** | About 40 manual checks | Confirms validity, name and address; no limit hit at normal speed | Yes, for confirming |
| Company websites | Crawler on 80 companies known to be registered, plus 40 random companies | 2 numbers out of 80; 0 out of 40 random | No |
| Web search (Google, manual) | Searches like "VAT Reg No" plus a company number | Found letterheads on other companies' sites and a council planning portal | Works by hand; no automated access |
| Brave Search API | Same searches automated | Ignored exact numbers and search operators | No |
| Council spending files | 4 councils of different types, 693,835 payments | 0 VAT numbers | No |
| Central government spending | HMRC's own spending file | Supplier postcodes, no VAT numbers | No |
| Find a Tender (government contracts) | 100 contract award notices | Suppliers identified by company number and a procurement ID, never by VAT number | No |
| The Gazette (official notices) | 20 search results, 9 opened | 2 VAT numbers, both from 2011 petitions against small partnerships | No |
| OpenCorporates | Read the terms | Has VAT numbers, but commercial use needs a paid licence | Only with a licence |
| VAT lookup directory sites | Found one by accident | Correct number shown, but the site refused connections and doesn't say where its data comes from | No |

### 1.4 Dead ends, and why

- **Company websites:** there is no legal requirement to show a VAT number on a UK website. Of 23 small-company sites crawled, 8 showed the company number and none showed a VAT number. A further 43% of companies had no website the crawler could find.
- **Council spending files:** the "VAT" column holds VAT *amounts*, not supplier VAT numbers. The only VAT-like strings were water-bill account numbers, and 2 of 5 even passed the checksum, which shows why a checksum alone proves nothing.
- **Government tenders:** suppliers are identified by company number and the new procurement ID, never by VAT number.
- **The Gazette:** HMRC quotes a VAT number only when it petitions to wind up a partnership, which has no company number. So the Gazette yields only old numbers of businesses being closed down.
- **Search APIs:** no automated access to an index good enough to find exact numbers.
- **Directory sites:** a correct number, but no stated source and no stable access, so not reproducible or licensable.
- **A trap worth recording:** a directory page about one UK company showed the directory's own Irish VAT number in its footer. A careless extractor would have assigned it to the UK company. Requiring a company number next to the VAT number prevents this.

### 1.5 One company, end to end

Autofix Accident Repair Centre Ltd (SC673813). Its filings on Companies House have no VAT field. Its accounts show profits growing by £292,000 in a year, so its turnover must be above the £90,000 registration threshold, and it must be registered. Its 5-page website has no legal details. A job advert mentioned VAT returns but no number. **The VAT number, GB359057474, appeared only in Peppol,** which the company had joined 27 days earlier. HMRC confirmed it. Lesson: a registered company can be invisible on the open web.

---

## Part 2 - Proof of concept

### 2.1 What I built

- **A Common Crawl scanner** that streams the crawl's text files, finds valid VAT numbers, and keeps those printed next to a labelled company number. It never stores the crawl itself, so it runs on a laptop.
- **A Peppol extractor** that pulls every UK VAT number out of the 19.6 GB directory export.
- **A company-website crawler** (finds a company's site, reads up to 10 pages and 5 PDFs, respects robots.txt, one request per second). It was tested and largely ruled out.
- **Shared accuracy rules** used by all three: correct format, checksum, the VAT number within 300 characters of the company's number (or postcode plus name), ambiguous pages rejected, and an HMRC check before anything counts as found.
- 37 automated tests built from real cases met during the research.

### 2.2 Main result: the Common Crawl sample

**Sample:** 50 files picked at random from the November 2026 crawl, which has 100,000 files in total. That is 1,079,230 web pages, about 0.05% of the crawl.

| | Count |
|---|---|
| Pages with a valid UK VAT number | 2,058 |
| ...that also show a company number nearby | 1,674 (81%) |
| Distinct VAT number + company number pairs | 1,269 |
| ...where the company number is an active company | 1,206 (95%) |
| Distinct VAT numbers in those | **1,196** |
| ...already in Peppol | 44 (4%) |

**Who it finds:** 57% small companies, 21% medium or large, 19% micro. Large companies are over-represented (2% of all companies), but small and micro companies still make up three quarters of the finds. The numbers came from 1,321 different websites, so no single directory drives the result.

**How big the full crawl is:** new numbers were still appearing at a steady ~24 per file, so 50 files can't show where the total levels off. The full crawl holds somewhere between several thousand and about 2.4 million pairs. 2.4 million is an upper bound, because big companies appear on many pages. Scanning a few hundred more files would narrow this.

Full details: [Experiment 03](docs/experiment-03-common-crawl.md).

### 2.3 The company-by-company crawler

| Test | Companies | Website found | VAT number found | Wrong numbers |
|---|---|---|---|---|
| Random companies (not dormant) | 40 | 13 | 0 | 0 |
| Known registered, small and micro | 40 | 23 | 0 | 0 |
| Known registered, medium and large | 40 | 23 | 2 (H.L. Hutchinson GB823841235, Classic Cottages GB268296752) | 0 |

"Known registered" companies come from Peppol: their VAT number was hidden from the crawler and used to mark its answers ([Experiment 02](docs/experiment-02-masked-peppol-test.md)). The crawler never attached a wrong number, but it almost never found one. The main failure is finding the right website at all.

### 2.4 HMRC-confirmed numbers and false-positive rates

Every number below was checked by hand on HMRC's service.

| Source | Checked | Invalid at HMRC | Valid but wrong company |
|---|---|---|---|
| Common Crawl pairs | 20 random pairs | 0 of 20 | 0 of 20 |
| Peppol, matched by company name | 17 random matches | 2 of 17 (12%), no longer registered | 1 of 15 (7%) |
| Company-website crawler | 2 numbers found | 0 of 2 | 0 of 2 |

**36 numbers are HMRC-confirmed** for the right company: 20 from Common Crawl, 14 from Peppol, 2 from the crawler. The 1,196 Common Crawl numbers are candidates. The 20/20 check suggests high accuracy, but with 20 checks the true error rate could still be as high as 16% (95% confidence). Checking a few hundred would narrow that to a few percent.

Two details behind these figures:
- In 2 of the 20 Common Crawl checks, HMRC showed the parent company's name (Primer Design shown as Novacyt UK Holdings; Harrison Leisure UK shown as Harrison Leisure Group). Both are VAT groups. I count them as correct, because the number legitimately covers that company.
- The Peppol wrong-company case came from name matching: "APM (Sales & Service) UK Ltd" was matched to "APM (Sales & Service) Ltd". Matching on company numbers avoids this, which is why the Common Crawl pairs are more reliable than name matches.

### 2.5 What these numbers don't tell you

- The samples are small (50 files, 20 to 80 companies), so every rate has a wide margin. I report the margins.
- Common Crawl only sees companies with websites, and favours larger ones. Micro companies without a website will not appear.
- Crawled pages can be months old. A number that was valid then may have been cancelled since, so every number must be re-checked with HMRC before use.
- PDF letterheads and text inside images were not scanned.

---

## Part 3 - With real resources

### 3.1 What I would build

```
  Companies House (monthly)        the list of every company, keyed by company number
          |
  Common Crawl (monthly)    --->   VAT number + company number pairs   --+
  Peppol directory (daily)  --->   VAT numbers matched by name/address --+--> HMRC check --> one table:
  Customer invoices         --->   VAT numbers read from invoices      --+                 company number -> VAT number(s),
                                                                                           source, evidence, date checked
          |
  Audit team                       checks a random sample every month, measures the error rate
```

Every source feeds the same table, keyed by company number. Nothing enters the table until HMRC confirms it, and the table records where each number came from and when it was last checked.

### 3.2 What each resource changes

| Resource | What I would use it for | Effect on coverage | Effect on accuracy |
|---|---|---|---|
| **A computing cluster** | Scan every file of each monthly Common Crawl, plus past crawls going back several years | **Largest gain.** The sample found 1,196 numbers in 0.05% of one crawl, still growing steadily. Past crawls may add companies whose current pages were missed or changed | High: pairs come with an exact company-number match |
| **HMRC check, at scale** | Confirm every candidate, then re-check all stored numbers monthly | None directly | **Largest gain:** removes invalid and cancelled numbers. The standard limit is 3 checks per second (about 260,000 a day), so a monthly re-check of 2 million numbers fits |
| **Peppol directory** | Daily download of new UK members | Small (about 1% of registrations), but growing and covering companies with no website | High, if matches require an HMRC name match, not just a similar name |
| **Annotation team** | Check a random 200 numbers a month, plus every VAT number that appears with more than one company | None | Turns "0 errors in 20" into a measured error rate within a few percent, and catches new error patterns early |
| **The customer's own invoices** | Read the VAT number printed on each supplier invoice | **Complete for the customer's suppliers.** Every supplier that has invoiced them has printed its number | High once each number is HMRC-checked |
| Commercial data sources | Licensed VAT data (e.g. OpenCorporates) for comparison and gap-filling | Moderate, depending on the licence | Useful as a second source to cross-check |
| Crawling budget and proxies | Not needed | The per-company crawler found 2 numbers in 80 companies. Common Crawl has already fetched the pages, so there is no need to visit sites or get around blocking | None |

### 3.3 How I would get there

1. **Full scan of one crawl.** Run the scanner over all 100,000 files of the latest crawl, close to where Common Crawl stores the data (Amazon's US-East region), so the 6 TiB is never downloaded. Join the pairs to Companies House and HMRC-check every distinct pair. This answers the open question from Part 2: how many companies the crawl actually covers.
2. **Measure against the customer.** Match the customer's 27,000 missing suppliers by company number to see how many the crawl fills. Add Peppol matches.
3. **Add past crawls.** Scan earlier crawls and keep only numbers HMRC still confirms. Stop when each extra crawl adds little.
4. **Fill the remainder from invoices.** For suppliers still missing, read the VAT number from their invoices.
5. **Run it monthly.** Scan each new crawl, take the daily Peppol updates, re-check every stored number with HMRC, and have the audit team check a sample.

### 3.4 What breaks first

1. **Companies without websites.** Common Crawl cannot find them. Invoices and Peppol are the only routes.
2. **VAT groups.** One number legitimately covers several companies, and HMRC shows only the lead company's name. The table must allow one number for several companies, or correct numbers will be rejected as errors.
3. **Old pages.** A number seen on a page last year may have been cancelled since. In the Peppol test, 2 of 17 numbers were no longer registered. Regular HMRC re-checks handle this.
4. **Name-only matches.** Without a company number, about 1 match in 15 picked the wrong company. Sources without a company number need an HMRC name and postcode match.
5. **Not a bottleneck: HMRC's limit.** At 3 checks per second, re-checking everything monthly fits easily.

### 3.5 What I would monitor

- The share of stored numbers that HMRC no longer confirms, each month.
- The wrong-company rate in the monthly audit.
- VAT numbers attached to several unrelated companies, after excluding known VAT groups.
- New, confirmed and disappeared numbers from each new Common Crawl.
- Coverage of the customer's supplier list, by company size.

---

## Beyond the UK: Germany

In Germany, finding the number is easier and checking it is harder, the reverse of the UK.

- **Finding it:** every German business website must have an "Impressum" (legal notice) page, and it must include the VAT number if the business has one (section 5 of the German Digital Services Act, DDG). Missing details can be fined up to €50,000. So the number that small UK sites leave out is required on German ones, on a page with a predictable name. The same scanner, with the German number format, should find far more. This is untested.
- **Checking it:** the EU's VAT checking service (VIES) confirms only whether a German number is valid. For data-protection reasons it returns no name or address, so you can only ask whether a name and address you already have matches.
- **What that means:** the link between number and company has to come from the page itself. An Impressum lists the commercial register number next to the VAT number, so the same rule used in the UK (VAT number next to company number) carries over.

---

## Appendix

- Experiment write-ups: [Experiment 01 - blind manual search](docs/experiment-01-blind-manual-search.md) · [Experiment 02 - masked Peppol test](docs/experiment-02-masked-peppol-test.md) · [Experiment 03 - Common Crawl](docs/experiment-03-common-crawl.md)
- Data used: Companies House company file (1 November 2026); Peppol directory export (23 November 2026); Common Crawl CC-MAIN-2026-47 (November 2026); HMRC checks done by hand, November 2026.
- Debate topics (checking every possible number, keeping data current, measuring errors, sources to avoid): see the [README](README.md#debate-topics).
- How to reproduce: see the README ("Data setup") and `crawler/README.md`.

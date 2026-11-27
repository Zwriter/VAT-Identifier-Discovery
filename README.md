# VAT Identifier Discovery

Can a UK company VAT dataset be built from the open web? Research and proof of concept for the
Veridion *Data Assets Intern* challenge.

The crawler tries, for a random sample of UK companies, to find each company's VAT number from open
sources, attaches it only when the evidence ties it to that company, verifies it against HMRC, and
records *why* it failed when it didn't. Details: [`crawler/README.md`](crawler/README.md).

## Repository layout

```
VAT Identifier/
├── REPORT.md              # the submission document
├── crawler/
│   ├── vatcrawl/          # core/ web/ routes/ prep/ run/ experiments/ (see crawler/README.md)
│   ├── scripts/           # Peppol Directory tools (preview + UK extract)
│   ├── tests/
│   └── README.md
├── docs/                  # experiment write-ups (Experiments 01–03)
├── data/                  # generated files (not in Git) — see data/README.md
├── unseen_data/           # raw downloads (not in Git)
├── .env.example           # copy to .env and add your keys
└── setup_venv.bat         # creates .venv and installs dependencies (Windows)
```

## Setup

```bat
setup_venv.bat              :: creates .venv, activates it, installs crawler\requirements.txt
copy .env.example .env      :: then fill in BRAVE_API_KEY and CRAWLER_USER_AGENT
.venv\Scripts\activate
```

## Data setup (required — not included in this repository)

The raw data is large (≈ 22 GB) and comes from third parties, so neither it nor anything derived
from it is committed. Download it into `unseen_data/` and run the steps below.

### 1. Companies House basic company data (free, Open Government Licence)

- Download **BasicCompanyDataAsOneFile-YYYY-MM-DD.zip** from
  https://download.companieshouse.gov.uk/en_output.html and unzip it into `unseen_data/`
  (≈ 2.8 GB CSV, ≈ 5.7 M companies; this project used the 2026-11-01 snapshot).
- Shrink it to the useful columns (≈ 80 s, low memory):

```bat
cd crawler
python -m vatcrawl.prep.slim_ch --ch ../unseen_data/BasicCompanyDataAsOneFile-2026-11-01.csv --out ../data/ch_slim.csv --active-only --drop-other-band
```

### 2. Peppol Directory export (e-invoicing registry; UK participants use their VAT number, scheme 9932)

- Download the full business-card export from the Peppol Directory:
  [Export data](https://directory.peppol.eu/public/locale-en_US/menuitem-docs-export-all).
  This project used the **JSON** export
  (≈ 19.6 GB, 9,763,490 entries, downloaded 2026-11-23) saved as `unseen_data/peppol.json`.
- Extract the UK entries (parallel scan, writes one row per UK participant):

```bat
python scripts\peppol_uk_fast.py ..\unseen_data\peppol.json -o ..\data\peppol_uk.csv
```

- Optional: inspect the structure / first UK entries:

```bat
python scripts\peppol_preview.py ..\unseen_data\peppol.json --uk -n 100
python scripts\peppol_preview.py ..\unseen_data\peppol.json --uk --count
```

### 3. Draw the sample

```bat
python -m vatcrawl.prep.sample --ch ../data/ch_slim.csv --per-band 10 --seed 42 --out ../data/sample.csv
```

### 4. Run

See [`crawler/README.md`](crawler/README.md) for the pipeline, HMRC verification and reporting steps.

## Debate topics

### 1. Why not just try every possible VAT number against HMRC?

Every VAT number has a built-in checksum, so only some 9-digit numbers are valid in form. I counted them: **20,615,843 of the 1 billion possible numbers pass (2.06%)**. With about 2.2 million real registrations, at most 1 in 9 of those is in use.

It is still a bad idea:
- **Too slow.** HMRC's API allows 3 checks per second. Checking all 20.6 million takes about 80 days, and the job would have to be repeated to stay current.
- **Misuse of a public service.** The checker exists so businesses can confirm a number they were given, not to reverse-engineer the register. A product built on it could be shut off at any time.
- **It doesn't solve the hard part.** HMRC returns a trading name and an address, not a company number. Linking that to the right company would need name matching, which picked the wrong company in about 1 case in 15 in my Peppol test.
- **There is a better route.** Common Crawl gives the VAT number together with the company number, which is the link this approach would lack.

### 2. How do you keep the dataset current?

- **Companies:** update from Companies House every month, adding new companies and removing dissolved ones.
- **New numbers:** scan each new monthly Common Crawl, and download Peppol's new UK members daily.
- **Old numbers:** re-check every stored number with HMRC every month. Numbers get cancelled: 2 of 17 Peppol numbers were no longer registered. 2 million checks take about 8 days at the standard limit, so a monthly cycle fits.
- **Where to look again:** new companies, and companies whose accounts show they have grown past the £90,000 registration threshold.

### 3. How do you know the data is wrong, at scale, without a list of correct answers?

- **Random audits:** a person checks a random sample every month (name, address, company number on the source page).
- **Warning signs in the data:** one VAT number attached to several unrelated companies (after excluding known VAT groups), HMRC's name not matching the company's name, and numbers that HMRC stops confirming.
- **Sources disagreeing:** when Common Crawl and Peppol give different numbers for the same company.
- **The customer's own answers:** the customer already holds VAT numbers for about 13,000 suppliers. Hiding them and checking whether the pipeline finds the same numbers is the closest thing to a ground-truth test this problem has. This is what Experiment 02 did with Peppol.

### 4. Which sources would I not use in a product?

- **VAT directory sites with no stated source:** I found one with a correct number, but it refused connections and does not say where its data comes from. You cannot rebuild it, audit it or license it.
- **OpenCorporates without a paid licence:** it holds UK VAT numbers, but the free terms require share-alike and attribution, and commercial use is paid.
- **Automated use of HMRC's web form:** the form is built for one-off human checks. Bulk checking should go through HMRC's API, within its limits.
- **Anything behind a login, or that needs bot-detection to be bypassed:** if a site does not want to be crawled, the data is not worth the legal and reputational risk.

## Licences and data use

- Companies House data: Open Government Licence v3.0.
- Peppol Directory data: published for participant discovery; personal data (sole traders' names,
  identifiers) is not extracted beyond what the analysis needs and is never committed.
- No search engine results page is scraped; search uses an official API or hand-collected results.

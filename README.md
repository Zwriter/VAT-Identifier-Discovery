# VAT Identifier Discovery

Can a UK company VAT dataset be built from the open web? Research and proof of concept for the
Veridion *Data Assets Intern* challenge.

The crawler tries, for a random sample of UK companies, to find each company's VAT number from open
sources, attaches it only when the evidence ties it to that company, verifies it against HMRC, and
records *why* it failed when it didn't. Details: [`crawler/README.md`](crawler/README.md).

## Repository layout

```
VAT Identifier/
├── crawler/
│   ├── vatcrawl/          # core/ web/ routes/ prep/ run/ experiments/ (see crawler/README.md)
│   ├── scripts/           # Peppol Directory tools (preview + UK extract)
│   ├── tests/
│   └── README.md
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

- Download the full business-card export from the Peppol Directory
  (https://directory.peppol.eu — "Export data"). This project used the **JSON** export
  (≈ 19.6 GB, 9,763,490 entries, downloaded 2026-11-23) saved as `unseen_data/peppol.json`.
  <!-- TODO: put the exact export URL you used here -->
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

## Licences and data use

- Companies House data: Open Government Licence v3.0.
- Peppol Directory data: published for participant discovery; personal data (sole traders' names,
  identifiers) is not extracted beyond what the analysis needs and is never committed.
- No search engine results page is scraped; search uses an official API or hand-collected results.

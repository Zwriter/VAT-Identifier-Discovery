# data/

Generated files live here. They are **not in Git** because they are derived from large
third-party downloads (see the main README, "Data setup"). Regenerate them with:

| File | Produced by |
|---|---|
| `peppol_uk.csv` | `crawler/scripts/peppol_uk_fast.py` on the Peppol Directory export |
| `ch_slim.csv`, `ch_slim_meta.json` | `python -m vatcrawl.slim_ch` on the Companies House file |
| `sample.csv`, `sample_meta.json` | `python -m vatcrawl.sample` (seed 42) |
| `domains.csv`, `manual_search.csv` | domain finder / manual search results |
| `results*.csv`, `*.jsonl` | `python -m vatcrawl.pipeline` and `python -m vatcrawl.report` |

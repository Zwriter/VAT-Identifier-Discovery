#!/usr/bin/env python3
"""
Scan a random sample of Common Crawl WET files for (UK VAT number, company number) pairs.

Nothing is stored except the matches: each WET file (~60 MB gzipped, ~20,000 pages of plain text)
is streamed, decompressed on the fly, scanned and discarded. Disk use stays near zero.

For every page it:
  1. finds checksum-valid GB VAT numbers (same rules as the crawler: GB prefix or a VAT label)
  2. looks for a *labelled* UK company number ("Company No", "Registered in England No", ...)
     within 300 characters of each VAT number -> an attributable pair
  3. (optional, --ch) checks the company number against the active Companies House file
     and adds its name + postcode, so pairs can be spot-checked on HMRC.

The files are a random slice of the crawl, so counts scale by (total files / files scanned).

Usage (from crawler/):
  python scripts/scan_common_crawl.py --files 50 --ch ../data/ch_slim.csv
  python scripts/scan_common_crawl.py --files 5                      # quick trial, no CH join
  python scripts/scan_common_crawl.py --summary                      # totals + 20 pairs to check on HMRC

Outputs:
  ../data/cc_pairs.csv   one row per (page, VAT, company number) pair
  ../data/cc_vats.csv    every checksum-valid VAT seen (with or without a company number)
  ../data/cc_stats.json  page counts, extrapolation to the full crawl, files done (for resuming)
  ../data/cc_hmrc_check.csv  (--summary) random pairs to verify by hand on HMRC

Re-running with the same --seed resumes: files already in cc_stats.json are skipped.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vatcrawl.config import load_env  # noqa: E402
from vatcrawl.core import vat as V  # noqa: E402

BASE = "https://data.commoncrawl.org/"
DEFAULT_CRAWL = "CC-MAIN-2026-47"
WINDOW = 300

# Quick byte-level filter before decoding a page: any VAT label or a GB+digits string.
PREFILTER = re.compile(rb"v\.?\s?a\.?\s?t|GB\s?\d{3}", re.I)

# A UK company number written next to a label. Up to 8 characters, optional 2-letter prefix.
RE_COMPANY_NO = re.compile(
    r"(?:company|registered|registration|reg\.?|incorporated|crn)"
    r"[^\d\n]{0,40}?"                                   # "... in England and Wales No."
    r"(?<![A-Z0-9])((?:SC|NI|OC|SO|NC|FC|GE|LP|SL|R0)?\d{6,8})(?![\d])",
    re.I,
)


# ------------------------------------------------------------------ WET parsing

def iter_wet_records(stream):
    """Yield (headers, body bytes) for each record of a (decompressed) WARC/WET stream."""
    while True:
        line = stream.readline()
        if not line:
            return
        if not line.startswith(b"WARC/"):
            continue
        headers: dict[str, str] = {}
        while True:
            h = stream.readline()
            if not h or h in (b"\r\n", b"\n"):
                break
            k, _, v = h.decode("utf-8", "replace").partition(":")
            headers[k.strip().lower()] = v.strip()
        n = int(headers.get("content-length", "0") or 0)
        body = stream.read(n)
        yield headers, body


# ------------------------------------------------------------------ extraction

def company_numbers(text: str) -> list[tuple[str, int]]:
    out = []
    for m in RE_COMPANY_NO.finditer(text):
        out.append((V.normalise_company_number(m.group(1)), m.start(1)))
    return out


def scan_page(text: str) -> tuple[list[V.VatCandidate], list[dict]]:
    """VAT candidates on the page + attributable pairs (VAT within WINDOW chars of a labelled company number)."""
    vats = V.find_vat_candidates(text)
    if not vats:
        return [], []
    cos = company_numbers(text)
    vat_spans = [(c.start, c.end) for c in vats]
    pairs = []
    for c in vats:
        best = None
        for num, pos in cos:
            if any(s <= pos < e for s, e in vat_spans):
                continue                      # the "company number" is part of a VAT number
            d = abs(pos - c.start)
            if d <= WINDOW and (best is None or d < best[1]):
                best = (num, d, pos)
        if best:
            lo = max(0, min(c.start, best[2]) - 60)
            hi = min(len(text), max(c.end, best[2]) + 60)
            pairs.append({
                "vat": c.vat, "company_number": best[0], "distance": best[1],
                "labelled": c.labelled,
                "snippet": re.sub(r"\s+", " ", text[lo:hi]).strip(),
            })
    return vats, pairs


# ------------------------------------------------------------------ I/O helpers

def wet_paths(crawl: str, cache: Path, session: requests.Session) -> list[str]:
    if cache.exists():
        return cache.read_text(encoding="utf-8").split()
    r = session.get(f"{BASE}crawl-data/{crawl}/wet.paths.gz", timeout=60)
    r.raise_for_status()
    paths = gzip.decompress(r.content).decode().split()
    cache.write_text("\n".join(paths), encoding="utf-8")
    return paths


def load_ch(path: str) -> dict[str, tuple[str, str]]:
    import pandas as pd
    print(f"Loading Companies House numbers from {path} (a minute)...", flush=True)
    df = pd.read_csv(path, usecols=["CompanyNumber", "CompanyName", "RegAddress.PostCode"],
                     dtype=str, keep_default_na=False)
    return {V.normalise_company_number(n): (name, pc)
            for n, name, pc in zip(df["CompanyNumber"], df["CompanyName"], df["RegAddress.PostCode"])}


def open_csv(path: Path, fields: list[str]):
    new = not path.exists()
    f = open(path, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(f, fieldnames=fields)
    if new:
        w.writeheader()
    return f, w


# ------------------------------------------------------------------ main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--files", type=int, default=50, help="number of WET files to scan (random sample)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--crawl", default=DEFAULT_CRAWL)
    ap.add_argument("--ch", help="ch_slim.csv: check company numbers against active companies")
    ap.add_argument("--out-dir", default="../data")
    ap.add_argument("--summary", action="store_true", help="summarise existing results instead of scanning")
    ap.add_argument("--check", type=int, default=20, help="pairs to sample for HMRC checking (with --summary)")
    args = ap.parse_args()
    if args.summary:
        summary(Path(args.out_dir), args.check, args.seed)
        return

    load_env()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stats_path = out / "cc_stats.json"

    s = requests.Session()
    s.headers["User-Agent"] = os.environ.get("CRAWLER_USER_AGENT") or "VATDiscoveryResearch/0.1"

    paths = wet_paths(args.crawl, out / f"cc_wet_paths_{args.crawl}.txt", s)
    sample = random.Random(args.seed).sample(paths, min(args.files, len(paths)))
    ch = load_ch(args.ch) if args.ch else None

    stats = json.loads(stats_path.read_text()) if stats_path.exists() else {
        "crawl": args.crawl, "total_files_in_crawl": len(paths), "files_done": [],
        "pages": 0, "pages_uk_domain": 0, "pages_prefilter": 0, "pages_with_vat": 0,
        "pages_with_pair": 0, "vat_mentions": 0, "pair_rows": 0,
    }
    done = set(stats["files_done"])

    pf, pw = open_csv(out / "cc_pairs.csv", ["vat", "company_number", "in_ch_active", "ch_name",
                                            "ch_postcode", "distance", "labelled", "url", "snippet", "wet_file"])
    vf, vw = open_csv(out / "cc_vats.csv", ["vat", "labelled", "uk_domain", "url", "wet_file"])

    try:
        for i, p in enumerate(sample, 1):
            if p in done:
                continue
            t0, pages, kept = time.time(), 0, 0
            for attempt in range(3):
                try:
                    r = s.get(BASE + p, stream=True, timeout=120)
                    r.raise_for_status()
                    stream = io.BufferedReader(gzip.GzipFile(fileobj=r.raw))
                    for h, body in iter_wet_records(stream):
                        if h.get("warc-type") != "conversion":
                            continue
                        pages += 1
                        url = h.get("warc-target-uri", "")
                        host = urlparse(url).hostname or ""
                        uk = host.endswith(".uk")
                        stats["pages_uk_domain"] += uk
                        if not PREFILTER.search(body):
                            continue
                        stats["pages_prefilter"] += 1
                        text = body.decode("utf-8", "replace")
                        vats, pairs = scan_page(text)
                        if not vats:
                            continue
                        stats["pages_with_vat"] += 1
                        stats["vat_mentions"] += len(vats)
                        for c in {c.vat: c for c in vats}.values():
                            vw.writerow({"vat": c.vat, "labelled": c.labelled, "uk_domain": uk, "url": url, "wet_file": p})
                        if pairs:
                            stats["pages_with_pair"] += 1
                        for pr in pairs:
                            name, pc = (ch.get(pr["company_number"]) if ch else None) or ("", "")
                            pw.writerow({**pr, "in_ch_active": (pr["company_number"] in ch) if ch else "",
                                         "ch_name": name, "ch_postcode": pc, "url": url, "wet_file": p})
                            stats["pair_rows"] += 1
                            kept += 1
                    break
                except (requests.RequestException, OSError, EOFError) as e:
                    print(f"  retry {attempt + 1}/3 after error: {e}", flush=True)
                    time.sleep(5 * (attempt + 1))
            else:
                print(f"  skipped {p}", flush=True)
                continue
            stats["pages"] += pages
            stats["files_done"].append(p)
            pf.flush(); vf.flush()
            stats_path.write_text(json.dumps(stats, indent=2))
            print(f"[{i}/{len(sample)}] {pages:,} pages, {kept} pairs, {time.time() - t0:.0f}s  "
                  f"(totals: {stats['pages']:,} pages, {stats['pages_with_vat']:,} with VAT, "
                  f"{stats['pair_rows']:,} pairs)", flush=True)
    finally:
        pf.close(); vf.close()

    n = len(stats["files_done"])
    if n:
        scale = stats["total_files_in_crawl"] / n
        stats["scale_factor"] = round(scale, 1)
        stats["extrapolated"] = {k: round(stats[k] * scale) for k in
                                 ("pages", "pages_with_vat", "pages_with_pair", "pair_rows")}
        stats_path.write_text(json.dumps(stats, indent=2))
        print(json.dumps({k: v for k, v in stats.items() if k != "files_done"}, indent=2))
    print("\nNext: python scripts/scan_common_crawl.py --summary")


def summary(out: Path, n_check: int, seed: int) -> None:
    import pandas as pd
    stats = json.loads((out / "cc_stats.json").read_text())
    pairs = pd.read_csv(out / "cc_pairs.csv", dtype=str, keep_default_na=False)
    vats = pd.read_csv(out / "cc_vats.csv", dtype=str, keep_default_na=False)
    files = len(stats["files_done"])
    scale = stats["total_files_in_crawl"] / max(files, 1)
    d = pairs.drop_duplicates(["vat", "company_number"])
    per_vat = d.groupby("vat")["company_number"].nunique()
    in_ch = d[d.in_ch_active == "True"] if "in_ch_active" in d and (d.in_ch_active != "").any() else None
    lines = [
        f"Files scanned: {files} of {stats['total_files_in_crawl']:,} (x{scale:,.0f} to extrapolate)",
        f"Pages: {stats['pages']:,}   on .uk domains: {stats['pages_uk_domain']:,}",
        f"Pages with a checksum-valid GB VAT: {stats['pages_with_vat']:,}   distinct VATs: {vats.vat.nunique():,}",
        f"Pages with an attributable pair:   {stats['pages_with_pair']:,}",
        f"Distinct (VAT, company number) pairs: {len(d):,}   distinct VATs in pairs: {d.vat.nunique():,}",
        f"VATs paired with more than one company number: {(per_vat > 1).sum():,}",
    ]
    if in_ch is not None:
        lines.append(f"Pairs whose company number is an ACTIVE company: {len(in_ch):,} "
                     f"({len(in_ch) / max(len(d), 1):.0%}); distinct VATs: {in_ch.vat.nunique():,}")
        base = in_ch
    else:
        base = d
    lines.append(f"Extrapolated distinct pairs (upper bound, duplicates across files ignored): ~{len(base) * scale:,.0f}")
    print("\n".join(lines))
    k = min(n_check, len(base))
    if k:
        chk = base.sample(k, random_state=seed)[["vat", "company_number", "ch_name", "ch_postcode", "url", "snippet"]]
        chk = chk.assign(hmrc_valid="", hmrc_name="", same_company="")
        chk.to_csv(out / "cc_hmrc_check.csv", index=False)
        print(f"\nWrote {k} random pairs to {out / 'cc_hmrc_check.csv'} -> check each on HMRC and fill "
              "hmrc_valid / hmrc_name / same_company (yes/no).")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Fast, parallel scan of a huge Peppol Directory JSON export for UK entries.

Instead of parsing the whole JSON document in one process, the file is cut into
byte ranges at entry boundaries (every entry has exactly one "pid" key) and the
ranges are scanned on all CPU cores. Each entry is first checked with a cheap
byte search; only possible UK entries are examined with regexes.

An entry counts as UK if:
  - an entity has countryCode "GB", or
  - its participant ID uses scheme 9932 (GB VAT), or
  - it lists a 9932 identifier among its extra identifiers.

Output:
  - <input>_uk.csv : one row per UK entry (pid scheme/value, GB VAT if any, name, country, regdate)
  - console summary: total entries, UK entries, how many carry a GB VAT number

Usage (Windows example):
  python peppol_uk_fast.py "D:\\path\\export.json"
  python peppol_uk_fast.py "D:\\path\\export.json" --workers 6 --chunk-mb 128

No third-party packages needed.
"""
import argparse
import collections
import csv
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

PID_TOKEN = b'"pid"'

# Cheap pre-filter: an entry can only be UK if one of these byte strings is in it.
PREFILTER = (b'"GB"', b'9932', b'"VAT"')

RE_PID = re.compile(rb'"pid"\s*:\s*"([^"]*)"')
RE_COUNTRY = re.compile(rb'"countryCode"\s*:\s*"([A-Za-z]{2})"')
RE_NAME = re.compile(rb'"name"\s*:\s*"((?:[^"\\]|\\.)*)"')
RE_REGDATE = re.compile(rb'"regdate"\s*:\s*"([^"]*)"')
# extra identifiers: {"scheme": X, "value": Y} in either key order
RE_IDENT = re.compile(
    rb'\{\s*"scheme"\s*:\s*"([^"]*)"\s*,\s*"value"\s*:\s*"([^"]*)"'
    rb'|\{\s*"value"\s*:\s*"([^"]*)"\s*,\s*"scheme"\s*:\s*"([^"]*)"'
)
GB_VAT_RE = re.compile(r"^(?:9932:)?GB ?(\d{9}|\d{12}|GD\d{3}|HA\d{3})$", re.I)
VAT_SCHEMES = {"9932", "VAT", "iso6523-actorid-upis"}
RE_DOCTYPES = re.compile(rb'"docTypes"')


def decode_json_string(b: bytes) -> str:
    """Decode a JSON string body (handles \\uXXXX and other escapes)."""
    import json
    try:
        return json.loads(b'"' + b + b'"')
    except Exception:
        return b.decode("utf-8", "replace")


def split_pid(pid: str):
    # "iso6523-actorid-upis::9932:gb123456789" -> ("9932", "gb123456789")
    tail = pid.split("::", 1)[-1]
    scheme, _, value = tail.partition(":")
    return scheme, value


def normalise_gb_vat(value: str) -> str:
    v = re.sub(r"[^0-9A-Za-z]", "", value).upper()
    if v.startswith("9932"):
        v = v[4:]
    return v if v.startswith("GB") else ("GB" + v if v else "")


def parse_entry(seg: bytes):
    """Return a dict for a UK entry, or None."""
    # Only look at the identity part, not the (long) docTypes list.
    m_doc = RE_DOCTYPES.search(seg)
    ident_part = seg[: m_doc.start()] if m_doc else seg

    m_pid = RE_PID.search(ident_part)
    if not m_pid:
        return None
    pid = m_pid.group(1).decode("utf-8", "replace")
    scheme, value = split_pid(pid)
    countries = [c.decode().upper() for c in RE_COUNTRY.findall(ident_part)]
    ident_vats = []
    for s1, v1, v2, s2 in RE_IDENT.findall(ident_part):
        sch = (s1 or s2).decode("utf-8", "replace")
        val = (v1 or v2).decode("utf-8", "replace").strip()
        if sch in VAT_SCHEMES and GB_VAT_RE.match(val.replace(" ", "")):
            ident_vats.append(val)

    uk = "GB" in countries or scheme == "9932" or bool(ident_vats)
    if not uk:
        return None

    vat = ""
    vat_source = ""
    if scheme == "9932":
        vat, vat_source = normalise_gb_vat(value), "participant_id"
    elif ident_vats:
        vat, vat_source = normalise_gb_vat(ident_vats[0]), "extra_identifier"

    m_name = RE_NAME.search(ident_part)
    m_reg = RE_REGDATE.search(ident_part)
    return {
        "pid_scheme": scheme,
        "pid_value": value,
        "gb_vat": vat,
        "vat_source": vat_source,
        "name": decode_json_string(m_name.group(1)) if m_name else "",
        "country": "|".join(sorted(set(countries))),
        "regdate": m_reg.group(1).decode() if m_reg else "",
    }


def find_next_pid(f, offset: int, file_size: int, block: int = 1 << 20) -> int:
    """Byte offset of the next PID_TOKEN at or after `offset` (or file_size)."""
    f.seek(offset)
    carry = b""
    pos = offset
    while pos < file_size:
        buf = f.read(block)
        if not buf:
            break
        data = carry + buf
        i = data.find(PID_TOKEN)
        if i != -1:
            return pos - len(carry) + i
        carry = data[-(len(PID_TOKEN) - 1):]
        pos += len(buf)
    return file_size


def scan_range(path: str, start: int, end: int):
    """Scan entries whose "pid" token starts in [start, end)."""
    rows, n_entries, n_candidates = [], 0, 0
    with open(path, "rb") as f:
        f.seek(start)
        data = f.read(end - start)
    # Every segment = one entry, from its "pid" to the next entry's "pid".
    positions = []
    i = data.find(PID_TOKEN)
    while i != -1:
        positions.append(i)
        i = data.find(PID_TOKEN, i + 1)
    positions.append(len(data))
    for a, b in zip(positions, positions[1:]):
        seg = data[a:b]
        n_entries += 1
        if not any(t in seg for t in PREFILTER):
            continue
        n_candidates += 1
        row = parse_entry(seg)
        if row:
            rows.append(row)
    return rows, n_entries, n_candidates


def make_ranges(path: Path, chunk_bytes: int):
    size = path.stat().st_size
    with path.open("rb") as f:
        first = find_next_pid(f, 0, size)
        bounds = [first]
        pos = first
        while True:
            nxt = find_next_pid(f, pos + chunk_bytes, size)
            if nxt >= size:
                bounds.append(size)
                break
            bounds.append(nxt)
            pos = nxt
    return list(zip(bounds, bounds[1:])), size


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", type=Path)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1),
                    help="Parallel processes (default: CPU cores - 1)")
    ap.add_argument("--chunk-mb", type=int, default=128, help="Bytes per work unit, in MB (default 128)")
    ap.add_argument("-o", "--output", type=Path, help="CSV output (default: <input>_uk.csv)")
    args = ap.parse_args()

    if not args.path.exists():
        sys.exit(f"File not found: {args.path}")

    out = args.output or args.path.with_name(args.path.stem + "_uk.csv")
    t0 = time.time()
    ranges, size = make_ranges(args.path, args.chunk_mb * 1024 * 1024)
    print(f"File: {size / 1e9:.1f} GB, {len(ranges)} chunks, {args.workers} workers")

    total = cands = done_bytes = 0
    fields = ["pid_scheme", "pid_value", "gb_vat", "vat_source", "name", "country", "regdate"]
    stats = collections.Counter()
    schemes = collections.Counter()

    with out.open("w", newline="", encoding="utf-8") as fcsv, \
            ProcessPoolExecutor(max_workers=args.workers) as pool:
        w = csv.DictWriter(fcsv, fieldnames=fields)
        w.writeheader()
        futs = {pool.submit(scan_range, str(args.path), s, e): (s, e) for s, e in ranges}
        for fut in as_completed(futs):
            s, e = futs[fut]
            rows, n, c = fut.result()
            total += n
            cands += c
            done_bytes += e - s
            for r in rows:
                w.writerow(r)
                stats["uk"] += 1
                stats["vat_" + (r["vat_source"] or "none")] += 1
                schemes[r["pid_scheme"]] += 1
            el = time.time() - t0
            print(f"  {done_bytes / size:6.1%}  entries {total:,}  UK {stats['uk']:,}  "
                  f"({el:.0f}s, {done_bytes / 1e6 / max(el, 1e-9):.0f} MB/s)", flush=True)

    el = time.time() - t0
    uk = stats["uk"]
    print("\n=== Summary ===")
    print(f"Entries scanned:        {total:,}  ({el:.0f}s)")
    print(f"Pre-filter candidates:  {cands:,}")
    print(f"UK entries:             {uk:,}  ({uk / max(total, 1):.3%} of all)")
    print(f"  GB VAT as participant ID (9932): {stats['vat_participant_id']:,}")
    print(f"  GB VAT as extra identifier:      {stats['vat_extra_identifier']:,}")
    print(f"  UK but no GB VAT number:         {stats['vat_none']:,}")
    print(f"Participant-ID schemes on UK entries: {schemes.most_common(10)}")
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()

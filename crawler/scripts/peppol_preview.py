#!/usr/bin/env python3
"""
Preview the first N entries of a huge Peppol Directory JSON export
without loading the whole file into memory.

Works with:
  - one big JSON document (e.g. {"...": [ {...}, {...} ]} or [ {...}, ... ])
  - JSON Lines (one JSON object per line)

Usage:
  pip install ijson
  python peppol_preview.py "D:\\path\\export.json"                 # first 100 entries
  python peppol_preview.py "D:\\path\\export.json" -n 500          # first 500
  python peppol_preview.py "D:\\path\\export.json" --uk           # first 100 UK entries (GB country or GB VAT scheme 9932)
  python peppol_preview.py "D:\\path\\export.json" --uk --count    # scan the WHOLE file and count UK entries (slow)
  python peppol_preview.py "D:\\path\\export.json" --match text    # plain substring filter (beware: matches inside other numbers)
  python peppol_preview.py "D:\\path\\export.json" -o preview.json # choose output file

Output: a pretty-printed JSON file with the entries, plus a short summary in the console.
"""
import argparse
import collections
import json
import re
import sys
import time
from decimal import Decimal
from pathlib import Path

try:
    import ijson
except ImportError:
    sys.exit("Missing dependency: run  pip install ijson")


def to_jsonable(o):
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    raise TypeError(f"Not JSON serializable: {type(o)}")


def is_json_lines(path: Path, probe_bytes: int = 4 * 1024 * 1024) -> bool:
    """
    True if the file starts with at least two lines that are each a complete
    JSON object. Reads only the first few MB, never a whole (possibly 19 GB) line.
    """
    with path.open("r", encoding="utf-8") as f:
        head = f.read(probe_bytes)
    lines = [l.strip() for l in head.split("\n")]
    complete = lines[:-1]  # the last piece may be cut off by the probe
    objs = [l for l in complete if l]
    if len(objs) < 2:
        return False
    try:
        return all(isinstance(json.loads(l), dict) for l in objs[:2])
    except json.JSONDecodeError:
        return False


def find_entries_prefix(path: Path, max_events: int = 200_000) -> str:
    """
    Stream the start of the file and return the ijson prefix of the first
    array whose items are objects (that's where the entries live).
    """
    with path.open("rb") as f:
        for i, (prefix, event, _) in enumerate(ijson.parse(f)):
            if event == "start_map" and prefix.endswith("item"):
                return prefix
            if i > max_events:
                break
    sys.exit("Couldn't find an array of objects near the start of the file. "
             "Run with --peek to inspect the structure.")


def schemes_of(entry: dict):
    """Participant-ID scheme plus any extra identifier schemes, e.g. {'0088', '9932'}."""
    out = set()
    pid = entry.get("pid", "")
    if "::" in pid:
        out.add(pid.split("::", 1)[1].split(":", 1)[0])
    for ent in entry.get("entities", []) or []:
        for ident in ent.get("identifiers", []) or []:
            if ident.get("scheme"):
                out.add(str(ident["scheme"]))
    return out


GB_VAT_RE = re.compile(r"^(?:9932:)?GB ?(\d{9}|\d{12}|GD\d{3}|HA\d{3})$", re.I)


def gb_vats_of(entry: dict):
    """GB VAT numbers from the participant ID or extra identifiers.
    Real exports use several spellings: scheme '9932', scheme 'VAT' with a GB value,
    or scheme 'iso6523-actorid-upis' with value '9932:GB...'."""
    found = []
    pid = entry.get("pid", "")
    tail = pid.split("::", 1)[-1]
    if tail.startswith("9932:"):
        found.append(tail[5:])
    for ent in entry.get("entities", []) or []:
        for ident in ent.get("identifiers", []) or []:
            sch, val = str(ident.get("scheme", "")), str(ident.get("value", "")).strip()
            if sch in ("9932", "VAT", "iso6523-actorid-upis") and GB_VAT_RE.match(val.replace(" ", "")):
                found.append(val)
    out = []
    for v in found:
        v = re.sub(r"[^0-9A-Za-z]", "", v).upper().removeprefix("9932")
        v = v if v.startswith("GB") else "GB" + v
        if v not in out:
            out.append(v)
    return out


def countries_of(entry: dict):
    return {ent.get("countryCode") for ent in entry.get("entities", []) or []}


def is_uk(entry: dict) -> bool:
    return "GB" in countries_of(entry) or "9932" in schemes_of(entry) or bool(gb_vats_of(entry))


def slim(entry: dict) -> dict:
    """Drop the long docTypes list; keep identity fields only."""
    e = {k: v for k, v in entry.items() if k != "docTypes"}
    e["docTypeCount"] = len(entry.get("docTypes", []) or [])
    return e


def iter_entries(path: Path):
    if is_json_lines(path):
        print("Format: JSON Lines")
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)
    else:
        prefix = find_entries_prefix(path)
        print(f"Format: single JSON document, entries at prefix '{prefix}'")
        with path.open("rb") as f:
            yield from ijson.items(f, prefix)


def peek(path: Path, n_events: int = 60):
    """Print the first parser events, to see the file's structure."""
    with path.open("rb") as f:
        for i, (prefix, event, value) in enumerate(ijson.parse(f)):
            v = "" if value is None else repr(value)[:80]
            print(f"{prefix:50} {event:12} {v}")
            if i + 1 >= n_events:
                break


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", type=Path, help="Path to the Peppol JSON export")
    ap.add_argument("-n", type=int, default=100, help="Number of entries to keep (default 100)")
    ap.add_argument("--uk", action="store_true", help="Keep only UK entries: country GB or GB VAT scheme 9932 (in the participant ID or extra identifiers)")
    ap.add_argument("--count", action="store_true", help="Scan the whole file and print counts (use with --uk); still saves the first N matches")
    ap.add_argument("--full", action="store_true", help="Keep the long docTypes list in the output")
    ap.add_argument("--match", help="Plain substring filter on the entry's JSON (beware: '9932' also matches inside other numbers)")
    ap.add_argument("-o", "--output", type=Path, help="Output file (default: <input>_preview.json)")
    ap.add_argument("--peek", action="store_true", help="Only print the first parser events and exit")
    args = ap.parse_args()

    if not args.path.exists():
        sys.exit(f"File not found: {args.path}")

    if args.peek:
        peek(args.path)
        return

    out = args.output or args.path.with_name(args.path.stem + "_preview.json")
    kept, scanned, t0 = [], 0, time.time()
    n_uk = n_uk_vat_pid = n_uk_vat_any = 0
    uk_country = collections.Counter()
    uk_schemes = collections.Counter()

    for entry in iter_entries(args.path):
        scanned += 1
        if args.count and scanned % 500_000 == 0:
            print(f"  scanned {scanned:,} entries, UK so far {n_uk:,} ({time.time() - t0:.0f}s)", flush=True)

        ok = True
        if args.uk:
            ok = is_uk(entry)
            if ok:
                n_uk += 1
                sch = schemes_of(entry)
                pid_scheme = entry.get("pid", "").split("::", 1)[-1].split(":", 1)[0]
                n_uk_vat_pid += pid_scheme == "9932"
                n_uk_vat_any += bool(gb_vats_of(entry))
                uk_schemes.update(sch)
                uk_country.update(c for c in countries_of(entry))
        if ok and args.match:
            ok = args.match in json.dumps(entry, default=to_jsonable, ensure_ascii=False)
        if not ok:
            if not args.count and scanned % 500_000 == 0:
                print(f"  scanned {scanned:,} entries, kept {len(kept)}...", flush=True)
            continue

        if len(kept) < args.n:
            kept.append(entry if args.full else slim(entry))
        if len(kept) >= args.n and not args.count:
            break

    with out.open("w", encoding="utf-8") as f:
        json.dump(kept, f, indent=2, ensure_ascii=False, default=to_jsonable)

    print(f"Scanned {scanned:,} entries in {time.time() - t0:.1f}s, kept {len(kept)}")
    if args.count and args.uk:
        print(f"UK entries (country GB or scheme 9932): {n_uk:,} of {scanned:,} ({n_uk / max(scanned, 1):.2%})")
        print(f"  participant ID is a GB VAT number (9932): {n_uk_vat_pid:,}")
        print(f"  GB VAT number anywhere (ID or extra identifiers): {n_uk_vat_any:,}")
        print(f"  schemes seen on UK entries: {uk_schemes.most_common(10)}")
        print(f"  country codes on UK entries: {uk_country.most_common(5)}")
    print(f"Saved to: {out}")
    if kept:
        first = kept[0]
        keys = list(first.keys()) if isinstance(first, dict) else type(first).__name__
        print(f"Top-level keys of the first entry: {keys}")


if __name__ == "__main__":
    main()

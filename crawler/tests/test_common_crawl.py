"""Common Crawl scanner: WET parsing and pair extraction on a synthetic WET file."""
import gzip
import importlib.util
import io
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "scan_common_crawl", Path(__file__).resolve().parents[1] / "scripts" / "scan_common_crawl.py")
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)


def _record(url: str, text: str, kind: str = "conversion") -> bytes:
    body = text.encode()
    head = (f"WARC/1.0\r\nWARC-Type: {kind}\r\nWARC-Target-URI: {url}\r\n"
            f"Content-Length: {len(body)}\r\n\r\n").encode()
    return head + body + b"\r\n\r\n"


def _wet(*records: bytes) -> io.BufferedReader:
    # real WET files are many concatenated gzip members
    raw = b"".join(gzip.compress(r) for r in records)
    return io.BufferedReader(gzip.GzipFile(fileobj=io.BytesIO(raw)))


def test_parses_concatenated_members():
    s = _wet(_record("https://a.co.uk/", "hello", "warcinfo"), _record("https://b.co.uk/", "world"))
    recs = list(cc.iter_wet_records(s))
    assert [h["warc-type"] for h, _ in recs] == ["warcinfo", "conversion"]
    assert recs[1][1] == b"world"


def test_pair_found_next_to_labelled_company_number():
    text = "Acme Ltd. Registered in England No. 01234567. VAT Reg No: 823 8412 35"
    vats, pairs = cc.scan_page(text)
    assert [v.vat for v in vats] == ["GB823841235"]
    assert pairs[0]["company_number"] == "01234567"


def test_unpadded_and_prefixed_company_numbers():
    vats, pairs = cc.scan_page("Company No: SC123456 | VAT GB823841235")
    assert pairs[0]["company_number"] == "SC123456"
    vats, pairs = cc.scan_page("Company number 1234567, VAT number GB 823 8412 35")
    assert pairs[0]["company_number"] == "01234567"


def test_vat_digits_are_not_taken_as_company_number():
    # "VAT Registration No 823841235": the label contains "Registration" but the digits are the VAT number
    vats, pairs = cc.scan_page("VAT Registration No 823841235")
    assert vats and not pairs


def test_far_apart_is_not_a_pair():
    text = "Company No 01234567. " + "x" * 400 + " VAT GB823841235"
    _, pairs = cc.scan_page(text)
    assert pairs == []


def test_invalid_checksum_ignored():
    vats, pairs = cc.scan_page("Company No 01234567 VAT GB123456789")
    assert vats == [] and pairs == []

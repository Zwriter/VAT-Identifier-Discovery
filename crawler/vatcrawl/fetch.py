"""
Polite HTTP fetching with robots.txt, per-host rate limiting, size limits, PDF text extraction
and a request log (one JSON line per request) so every result is traceable.
"""
from __future__ import annotations

import io
import json
import time
import urllib.robotparser
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None

import os

from .config import load_env

load_env()
DEFAULT_UA = os.environ.get("CRAWLER_USER_AGENT") or \
    "VATDiscoveryResearch/0.1 (personal research project; contact via GitHub repo)"


@dataclass
class Page:
    url: str
    status: int
    kind: str                 # html | pdf | xml | other | error
    text: str = ""
    links: list[str] = field(default_factory=list)
    error: str = ""


class Fetcher:
    def __init__(self, log_path: str | Path | None = None, user_agent: str = DEFAULT_UA,
                 delay: float = 1.0, timeout: float = 15.0, max_bytes: int = 5_000_000,
                 max_pdf_pages: int = 15):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = user_agent
        self.ua = user_agent
        self.delay, self.timeout, self.max_bytes, self.max_pdf_pages = delay, timeout, max_bytes, max_pdf_pages
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.log_path = Path(log_path) if log_path else None
        self.requests_made = 0
        self.bytes_read = 0
        self.company = ""      # set by the pipeline for logging

    # -------------------------------------------------------------- helpers
    def _log(self, **rec):
        if self.log_path:
            rec["t"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            rec["company"] = self.company
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _wait(self, host: str):
        last = self._last.get(host, 0.0)
        gap = time.time() - last
        if gap < self.delay:
            time.sleep(self.delay - gap)
        self._last[host] = time.time()

    def allowed(self, url: str) -> bool:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                self._wait(p.netloc)
                r = self.s.get(base + "/robots.txt", timeout=self.timeout)
                self.requests_made += 1
                self._log(url=base + "/robots.txt", status=r.status_code, bytes=len(r.content), note="robots")
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except requests.RequestException:
                rp.parse([])
            self._robots[base] = rp
        rp = self._robots[base]
        return rp.can_fetch(self.ua, url) if rp else True

    def robots_sitemaps(self, base: str) -> list[str]:
        self.allowed(base + "/")
        rp = self._robots.get(base)
        return list(rp.site_maps() or []) if rp else []

    # ---------------------------------------------------------------- fetch
    def get(self, url: str) -> Page:
        if not self.allowed(url):
            self._log(url=url, status=0, note="robots_disallow")
            return Page(url, 0, "error", error="robots_disallow")
        host = urlparse(url).netloc
        self._wait(host)
        try:
            r = self.s.get(url, timeout=self.timeout, stream=True, allow_redirects=True)
            self.requests_made += 1
            data = b""
            for chunk in r.iter_content(65536):
                data += chunk
                if len(data) > self.max_bytes:
                    break
            self.bytes_read += len(data)
        except requests.RequestException as e:
            self._log(url=url, status=0, error=type(e).__name__)
            return Page(url, 0, "error", error=type(e).__name__)

        ctype = r.headers.get("Content-Type", "").lower()
        final = r.url
        self._log(url=url, final=final, status=r.status_code, bytes=len(data), ctype=ctype[:40])
        if r.status_code >= 400:
            return Page(final, r.status_code, "error", error=f"http_{r.status_code}")
        if "pdf" in ctype or final.lower().endswith(".pdf") or data[:5] == b"%PDF-":
            return Page(final, r.status_code, "pdf", text=self._pdf_text(data))
        if "xml" in ctype and "html" not in ctype:
            return Page(final, r.status_code, "xml", text=data.decode(r.encoding or "utf-8", "replace"))
        if "html" in ctype or data.lstrip()[:1] == b"<":
            html = data.decode(r.encoding or "utf-8", "replace")
            text, links = html_text_and_links(html, final)
            return Page(final, r.status_code, "html", text=text, links=links)
        return Page(final, r.status_code, "other")

    def _pdf_text(self, data: bytes) -> str:
        if PdfReader is None:
            return ""
        try:
            reader = PdfReader(io.BytesIO(data))
            parts = []
            for page in reader.pages[: self.max_pdf_pages]:
                parts.append(page.extract_text() or "")
            return "\n".join(parts)
        except Exception:
            return ""


def html_text_and_links(html: str, base_url: str) -> tuple[str, list[str]]:
    if BeautifulSoup is None:
        import re
        text = re.sub(r"<[^>]+>", " ", html)
        links = [urljoin(base_url, h) for h in re.findall(r'href=["\']([^"\']+)', html)]
        return " ".join(text.split()), links
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    links = [urljoin(base_url, a["href"]) for a in soup.find_all("a", href=True)]
    text = soup.get_text(" ")
    return " ".join(text.split()), links

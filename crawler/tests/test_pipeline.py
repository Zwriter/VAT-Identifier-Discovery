"""
End-to-end test on local fake sites modelled on real cases:
  - LGM-style site: sitemap, contact page with footer VAT, linked Declaration of Performance PDF
  - Autofix-style site: 5-page template, no legal details (but Autofix is in Peppol)
  - Directory page about a company showing the directory's own foreign VAT in its footer
  - Manual search results: Sammons-style snippet with company number + VAT
"""
import csv
import functools
import http.server
import io
import threading

import pytest

from vatcrawl.run import pipeline


def _pdf_bytes(text: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in text.splitlines():
        c.drawString(40, y, line)
        y -= 16
    c.save()
    return buf.getvalue()


SITES = {
    "lgm": {
        "/": "<html><body><h1>LGM Products</h1><a href='/contact/'>Contact</a><a href='/products/'>Products</a>"
             "<footer>LGM Products Ltd registered in England number 3574049</footer></body></html>",
        "/sitemap.xml": "<?xml version='1.0'?><urlset><url><loc>{base}/</loc></url><url><loc>{base}/contact/</loc></url>"
                        "<url><loc>{base}/products/</loc></url></urlset>",
        "/contact/": "<html><body>Registered company details: LGM Products Ltd, number 3574049, "
                     "VAT number 709112069. Unit 3, Quantum Business Park, Fleet GU52 8EA</body></html>",
        "/products/": "<html><body><a href='/docs/declaration-of-performance.pdf'>DoP</a></body></html>",
    },
    "autofix": {
        "/": "<html><body>Autofix Accident Repair Centre. Welcome! <a href='/contact'>Contact</a></body></html>",
        "/sitemap.xml": "<?xml version='1.0'?><urlset><url><loc>{base}/home</loc></url><url><loc>{base}/contact</loc></url>"
                        "<url><loc>{base}/our-services</loc></url><url><loc>{base}/reviews</loc></url></urlset>",
        "/home": "<html><body>Accident repairs in Loanhead</body></html>",
        "/contact": "<html><body>Call us. Loanhead EH20 9QH</body></html>",
        "/our-services": "<html><body>Bodywork, paint</body></html>",
        "/reviews": "<html><body>Great service!</body></html>",
    },
    "directory": {
        "/": "<html><body>LGM Products Ltd. Company number 03574049. Fleet GU52 8EA. "
             + "filler " * 200 + "<footer>Sama Talent Group VAT IE 4719881IH</footer></body></html>",
    },
}
PDF_TEXT = ("LGM Products Ltd   Registered in England: 3574049\n"
            "VAT Reg No: 709 1120 69   EORI: GB709112069000\n"
            "Declaration of Performance")


class Handler(http.server.BaseHTTPRequestHandler):
    def __init__(self, *a, site=None, **kw):
        self.site = site
        super().__init__(*a, **kw)

    def log_message(self, *a):
        pass

    def do_GET(self):
        base = f"http://{self.headers['Host']}"
        path = self.path.split("?")[0]
        if path.endswith(".pdf") and self.site == "lgm":
            body, ctype = _pdf_bytes(PDF_TEXT), "application/pdf"
        elif path in SITES[self.site]:
            body = SITES[self.site][path].format(base=base).encode()
            ctype = "application/xml" if path.endswith(".xml") else "text/html; charset=utf-8"
        else:
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def servers():
    ports = {}
    srvs = []
    for name in SITES:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, site=name))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        ports[name] = srv.server_address[1]
        srvs.append(srv)
    yield ports
    for s in srvs:
        s.shutdown()


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def test_end_to_end(tmp_path, servers):
    sample = tmp_path / "sample.csv"
    _write_csv(sample, [
        {"CompanyName": "LGM PRODUCTS LIMITED", "CompanyNumber": "03574049", "RegAddress.PostCode": "GU52 8EA",
         "Accounts.AccountCategory": "TOTAL EXEMPTION FULL", "CompanyStatus": "Active"},
        {"CompanyName": "AUTOFIX ACCIDENT REPAIR CENTRE LTD", "CompanyNumber": "SC673813", "RegAddress.PostCode": "EH20 9QH",
         "Accounts.AccountCategory": "UNAUDITED ABRIDGED", "CompanyStatus": "Active"},
        {"CompanyName": "SAMMONS ARCHITECTURAL LIMITED", "CompanyNumber": "09351572", "RegAddress.PostCode": "ST13 6JP",
         "Accounts.AccountCategory": "MICRO ENTITY", "CompanyStatus": "Active"},
        {"CompanyName": "QUIET SHELL LTD", "CompanyNumber": "12345678", "RegAddress.PostCode": "SW1A 1AA",
         "Accounts.AccountCategory": "DORMANT", "CompanyStatus": "Active"},
        {"CompanyName": "NO SITE TRADING LTD", "CompanyNumber": "07654321", "RegAddress.PostCode": "M1 1AA",
         "Accounts.AccountCategory": "MICRO ENTITY", "CompanyStatus": "Active"},
    ])
    peppol = tmp_path / "peppol_uk.csv"
    _write_csv(peppol, [{"pid_scheme": "9932", "pid_value": "gb359057474", "gb_vat": "GB359057474",
                         "vat_source": "participant_id", "name": "AUTOFIX ACCIDENT REPAIR CENTRE", "country": "GB",
                         "regdate": "2026-10-27"}])
    domains = tmp_path / "domains.csv"
    _write_csv(domains, [{"company_number": "03574049", "domain": f"http://127.0.0.1:{servers['lgm']}"}])
    search = tmp_path / "search.csv"
    _write_csv(search, [{"query": '"09351572" "VAT Reg"', "rank": "1", "url": "http://publicaccess.example.gov.uk/doc.pdf",
                         "title": "Registered in England No 09351572 V.A.T. Reg. No. 202 ...",
                         "snippet": "Registered in England No 09351572. V.A.T. Reg. No. 202 5358 43. 10 Cawdry Buildings. "
                                    "Fountain Street. Leek. Staffordshire. ST13 6JP."}])
    out = tmp_path / "results.csv"
    pipeline.main(["--sample", str(sample), "--peppol", str(peppol), "--domains", str(domains),
                   "--search-csv", str(search), "--out", str(out), "--log", str(tmp_path / "log.jsonl"),
                   "--delay", "0", "--routes", "peppol,website,search"])
    res = {r["company_number"]: r for r in csv.DictReader(open(out))}

    lgm = res["03574049"]
    assert lgm["outcome"] == "found_unverified" and lgm["vat"] == "GB709112069" and lgm["route"] == "website"
    assert lgm["evidence"] == "company_number_adjacent"

    auto = res["SC673813"]
    assert auto["vat"] == "GB359057474" and auto["route"] == "peppol"

    sam = res["09351572"]
    assert sam["vat"] == "GB202535843" and sam["route"] == "search" and sam["reason"] == "search_snippet"

    assert res["12345678"]["outcome"] == "probably_not_registered"
    assert res["07654321"]["outcome"] == "unknown" and res["07654321"]["reason"] == "no_website_found"
    assert (tmp_path / "log.jsonl").read_text().count("\n") > 3


def test_template_site_without_vat(servers):
    from vatcrawl.core.attribute import Target
    from vatcrawl.web.fetch import Fetcher
    from vatcrawl.routes.website import crawl_site
    r = crawl_site(Fetcher(delay=0), f"http://127.0.0.1:{servers['autofix']}",
                   Target("SC673813", "AUTOFIX ACCIDENT REPAIR CENTRE LTD", "EH20 9QH"))
    assert r.decision is None and r.reason == "site_no_vat"


def test_pdf_letterhead_found_when_page_has_no_vat(servers):
    """Remove the VAT from the contact page: the crawler must still find it in the linked PDF."""
    from vatcrawl.core.attribute import Target
    from vatcrawl.web.fetch import Fetcher
    from vatcrawl.routes.website import crawl_site
    saved = SITES["lgm"]["/contact/"]
    SITES["lgm"]["/contact/"] = "<html><body>Contact us</body></html>"
    try:
        r = crawl_site(Fetcher(delay=0), f"http://127.0.0.1:{servers['lgm']}",
                       Target("03574049", "LGM PRODUCTS LIMITED", "GU52 8EA"))
    finally:
        SITES["lgm"]["/contact/"] = saved
    assert r.decision and r.decision.vat == "GB709112069" and r.source_url.endswith(".pdf")


def test_directory_footer_vat_rejected(servers):
    from vatcrawl.core.attribute import Target, best, judge
    from vatcrawl.web.fetch import Fetcher
    p = Fetcher(delay=0).get(f"http://127.0.0.1:{servers['directory']}/")
    assert best(judge(p.text, Target("03574049", "LGM PRODUCTS LIMITED", "GU52 8EA"))) is None


def test_unreachable_site_is_not_reported_as_empty():
    from vatcrawl.core.attribute import Target
    from vatcrawl.web.fetch import Fetcher
    from vatcrawl.routes.website import crawl_site
    r = crawl_site(Fetcher(delay=0, timeout=2), "http://127.0.0.1:9", Target("03574049", "LGM PRODUCTS LIMITED"))
    assert r.reason.startswith("fetch_error")


def test_site_signal_needs_identity(servers):
    """A pricing phrase counts only on a site that names the company."""
    from vatcrawl.core.attribute import Target
    from vatcrawl.web.fetch import Fetcher
    from vatcrawl.routes.website import crawl_site
    saved = dict(SITES["autofix"])
    SITES["autofix"]["/our-services"] = "<html><body>Bodywork from £300 + VAT</body></html>"
    try:
        ok = crawl_site(Fetcher(delay=0), f"http://127.0.0.1:{servers['autofix']}",
                        Target("SC673813", "AUTOFIX ACCIDENT REPAIR CENTRE LTD", "EH20 9QH"))
        other = crawl_site(Fetcher(delay=0), f"http://127.0.0.1:{servers['autofix']}",
                           Target("10932374", "MEADGATE POOL LIMITED", "CM2 7NS"))
    finally:
        SITES["autofix"].clear(); SITES["autofix"].update(saved)
    assert ok.identity_confirmed and ok.signal and ok.signal.kind == "registered"
    assert not other.identity_confirmed and other.signal is None

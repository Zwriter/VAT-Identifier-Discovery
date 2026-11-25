import csv

from vatcrawl.experiments import peppol_test
from vatcrawl.prep import slim_ch


def _w(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def test_build_and_evaluate(tmp_path, capsys):
    raw = tmp_path / "ch.csv"
    base = {"RegAddress.AddressLine1": "1 St", "RegAddress.PostTown": "TOWN", "CompanyCategory": "Private Limited Company",
            "CompanyStatus": "Active", "IncorporationDate": "01/01/2010", "SICCode.SicText_1": "x",
            "Mortgages.NumMortCharges": "0", "Accounts.LastMadeUpDate": "", "PreviousName_1.CompanyName": "",
            "RegAddress.AddressLine2": ""}
    _w(raw, [
        dict(base, CompanyName="LGM PRODUCTS LIMITED", CompanyNumber="03574049", **{"RegAddress.PostCode": "GU52 8EA", "Accounts.AccountCategory": "TOTAL EXEMPTION FULL"}),
        dict(base, CompanyName="AUTOFIX ACCIDENT REPAIR CENTRE LTD", CompanyNumber="SC673813", **{"RegAddress.PostCode": "EH20 9QH", "Accounts.AccountCategory": "UNAUDITED ABRIDGED"}),
        dict(base, CompanyName="DALE TECHNICHE LIMITED", CompanyNumber="04955915", **{"RegAddress.PostCode": "BB9 7QZ", "Accounts.AccountCategory": "MICRO ENTITY"}),
        dict(base, CompanyName="TWIN CO LTD", CompanyNumber="00000001", **{"RegAddress.PostCode": "M1 1AA", "Accounts.AccountCategory": "MICRO ENTITY"}),
        dict(base, CompanyName="TWIN CO LIMITED", CompanyNumber="00000002", **{"RegAddress.PostCode": "M2 1AA", "Accounts.AccountCategory": "MICRO ENTITY"}),
    ])
    slim = tmp_path / "slim.csv"
    slim_ch.main(["--ch", str(raw), "--out", str(slim), "--active-only"])
    peppol = tmp_path / "peppol.csv"
    _w(peppol, [
        {"gb_vat": "GB709112069", "name": "LGM PRODUCTS LTD", "regdate": "2025-01-01"},
        {"gb_vat": "GB359057474", "name": "AUTOFIX ACCIDENT REPAIR CENTRE", "regdate": "2026-10-27"},
        {"gb_vat": "GB824571526", "name": "Dale Techniche Ltd", "regdate": "2024-01-01"},
        {"gb_vat": "GB934219330", "name": "TWIN CO", "regdate": ""},          # ambiguous in CH -> excluded
        {"gb_vat": "GB222222222", "name": "Päppöl Täst", "regdate": ""},       # invalid + test -> excluded
    ])
    s, t = tmp_path / "s.csv", tmp_path / "t.csv"
    peppol_test.main(["build", "--peppol", str(peppol), "--ch", str(slim), "--n", "10", "--seed", "1",
                      "--out-sample", str(s), "--out-truth", str(t)])
    truth = list(csv.DictReader(open(t)))
    assert {r["company_number"] for r in truth} == {"03574049", "SC673813", "04955915"}
    assert "gb_vat" not in open(s).readline() and "GB709112069" not in open(s).read()

    res = tmp_path / "res.csv"
    _w(res, [
        {"company_number": "03574049", "vat": "GB709112069", "route": "website", "reason": "website", "website_reason": "found", "domain": "lgmproducts.com", "source_url": "u", "evidence": "company_number_adjacent"},
        {"company_number": "SC673813", "vat": "", "route": "", "reason": "site_no_vat", "website_reason": "site_no_vat", "domain": "autofixarc.com", "source_url": "", "evidence": ""},
        {"company_number": "04955915", "vat": "GB934219330", "route": "website", "reason": "website", "website_reason": "found", "domain": "x", "source_url": "u2", "evidence": "company_number_adjacent"},
    ])
    m = peppol_test.main(["evaluate", "--results", str(res), "--truth", str(t)])
    assert m == {"n": 3, "correct": 1, "wrong": 1}
    assert "Disagreements" in capsys.readouterr().out

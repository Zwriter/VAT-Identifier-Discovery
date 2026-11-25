"""Tests built from real cases found during research (see Experiment 01 and Findings notes)."""
from vatcrawl import vat as V
from vatcrawl.attribute import Target, judge, best, template_numbers


# ---------------------------------------------------------------- checksum
def test_checksum_known_valid_numbers():
    for n in ["709112069",   # LGM Products (HMRC confirmed)
              "824571526",   # Dale Techniche (HMRC confirmed)
              "202535843",   # Sammons Architectural (HMRC confirmed, post-2010 series)
              "359057474",   # Autofix Accident Repair Centre (HMRC confirmed)
              "934219330"]:  # Augis Trading (HMRC confirmed)
        assert V.vat_checksum_ok(n), n


def test_checksum_rejects_test_and_garbage():
    assert not V.vat_checksum_ok("222222222")   # Peppol test entry
    assert not V.vat_checksum_ok("333333333")   # Peppol test entry
    assert not V.vat_checksum_ok("12345678")    # too short


def test_normalise_vat_formats():
    assert V.normalise_vat("709 1120 69") == "GB709112069"
    assert V.normalise_vat("GB 824 5715 26") == "GB824571526"
    assert V.normalise_vat("9932:GB391532058") is None or V.normalise_vat("9932:GB391532058").startswith("GB")
    assert V.normalise_vat("GB03079239") is None     # a company number registered as VAT in Peppol


# ---------------------------------------------------------- extraction
LGM_LETTERHEAD = """LGM Products Ltd   Registered in England: 3574049
Unit 15 Riverside Industrial Park   VAT Reg No: 709 1120 69
Dogflud Way, Farnham   Fax: +44 (0) 1252 727627
Surrey GU9 7UG   EORI: GB709112069000
Declaration of Performance According to Construction Product Regulation EU No.305/2011"""

DALE_FOOTER = "For and on behalf of Dale Techniche Ltd. ... Registered in England No .4955915 VAT Reg No: 824 5715 26"

SAMMONS_SNIPPET = ("5 sept. 2018 — Registered in England No 09351572. V.A.T. Reg. No. 202 5358 43. "
                   "10 Cawdry Buildings. Fountain Street. Leek. Staffordshire. ST13 6JP. Tel: 01538 ...")

SAMA_PAGE = ("LGM Products Ltd. Company number 03574049. Registered office Unit 3, Quantum Business Park, "
             "Fleet GU52 8EA. Activity SIC 46140. " + "x " * 400 +
             "© Sama Talent Group. VAT IE 4719881IH")


def test_extracts_unprefixed_labelled_vat():
    vats = [c.vat for c in V.find_vat_candidates(LGM_LETTERHEAD)]
    assert "GB709112069" in vats


def test_eori_contains_vat():
    # EORI = GB + VAT + 000 ; the 12-digit form is a branch-style number, but its first 9 digits are the VAT
    assert V.vat_checksum_ok("709112069")


def test_eori_maps_to_vat_and_label_does_not_leak():
    cands = V.find_vat_candidates("EORI: GB709112069000 then later GB824571526 alone")
    assert [(c.vat, c.labelled) for c in cands] == [("GB709112069", True), ("GB824571526", False)]


def test_eori_group_member_suffix_not_guessed():
    assert V.find_vat_candidates("EORI GB709112069001") == []


def test_irish_vat_is_ignored():
    assert V.find_vat_candidates("VAT IE 4719881IH") == []


def test_dotted_label_and_spaces():
    assert [c.vat for c in V.find_vat_candidates(SAMMONS_SNIPPET)] == ["GB202535843"]


# ------------------------------------------------------ company numbers
def test_company_number_padding_and_variants():
    assert V.normalise_company_number("3574049") == "03574049"
    assert V.normalise_company_number("SC673813") == "SC673813"
    assert "3574049" in V.company_number_variants("03574049")
    assert V.find_company_number(DALE_FOOTER, "04955915")  # "No .4955915"


# --------------------------------------------------------------- names
def test_name_normalisation_keeps_uk():
    assert not V.names_match("APM (SALES & SERVICE) UK LIMITED", "APM (SALES & SERVICE) LTD")


def test_name_match_without_ltd():
    assert V.names_match("AUTOFIX ACCIDENT REPAIR CENTRE LTD", "AUTOFIX ACCIDENT REPAIR CENTRE")
    assert V.names_match("Dale Techniche Ltd", "DALE TECHNICHE LIMITED")


# ------------------------------------------------------------ postcodes
def test_postcode_district():
    assert V.postcode_district("GU52 8EA") == V.postcode_district("GU52 8DY") == "GU52 8"
    assert V.postcode_district("ST13 6JP") == "ST13 6"


# ---------------------------------------------------------- attribution
def test_lgm_letterhead_accepted_by_company_number():
    d = best(judge(LGM_LETTERHEAD, Target("03574049", "LGM Products Ltd", "GU52 8EA")))
    assert d and d.vat == "GB709112069" and d.evidence == "company_number_adjacent"


def test_dale_accepted():
    d = best(judge(DALE_FOOTER, Target("04955915", "Dale Techniche Ltd", "BB9 7QZ")))
    assert d and d.vat == "GB824571526"


def test_sammons_snippet_accepted():
    d = best(judge(SAMMONS_SNIPPET, Target("09351572", "Sammons Architectural Limited", "ST13 6JP")))
    assert d and d.vat == "GB202535843"


def test_wrong_company_rejected():
    # LGM's letterhead must not be attributed to another company
    assert best(judge(LGM_LETTERHEAD, Target("04955915", "Dale Techniche Ltd", "BB9 7QZ"))) is None


def test_directory_footer_not_attributed():
    # Sama's own IE VAT is ignored; nothing to attribute to LGM on that page
    assert best(judge(SAMA_PAGE, Target("03574049", "LGM Products Ltd", "GU52 8EA"))) is None


def test_template_detection():
    pages = [f"page {i} content ... footer VAT GB709112069" for i in range(3)]
    assert template_numbers(pages) == {"GB709112069"}


def test_report_finalise():
    from vatcrawl.report import finalise, wilson
    base = {"company_name": "AUTOFIX ACCIDENT REPAIR CENTRE LTD", "postcode": "EH20 9QH",
            "outcome": "found_unverified", "registration_evidence": ""}
    ok = finalise(dict(base, hmrc_status="valid", hmrc_name="AUTOFIX ACCIDENT REPAIR CENTRE", hmrc_postcode="EH20 9QH"))
    assert ok["outcome"] == "found_verified"
    wrong = finalise(dict(base, company_name="APM (SALES & SERVICE) UK LIMITED", hmrc_status="valid",
                          hmrc_name="APM (SALES & SERVICE) LTD", hmrc_postcode="BA2 6LY"))
    assert wrong["outcome"] == "found_wrong_company"
    assert finalise(dict(base, hmrc_status="not_found"))["outcome"] == "found_invalid"
    assert finalise(dict(base, outcome="unknown", registration_evidence="job ad"))["outcome"] == "registered_not_found"
    lo, hi = wilson(2, 17)
    assert 0.02 < lo < 0.05 and 0.3 < hi < 0.36


def test_domain_similarity():
    from vatcrawl.find_domains import similarity, is_directory, domain_label
    assert domain_label("www.lgmproducts.com") == "lgmproducts"
    assert domain_label("shop.example.co.uk") == "example"
    assert similarity("LGM PRODUCTS LIMITED", "www.lgmproducts.com") >= 0.5
    assert similarity("AUTOFIX ACCIDENT REPAIR CENTRE LTD", "www.autofixarc.com") >= 0.5   # initials
    assert similarity("DALE TECHNICHE LIMITED", "www.dale-techniche.co.uk") == 1.0
    assert similarity("LGM PRODUCTS LIMITED", "www.monsterenergy.com") < 0.5
    assert is_directory("find-and-update.company-information.service.gov.uk")
    assert is_directory("www.endole.co.uk")

from vatcrawl.core.signals import find_signal


def test_registered_phrases():
    for t in ["All prices exclude VAT. Every plan includes full code ownership.",   # Nettex.io (real)
              "Website audit from £450 + VAT", "Rates: £35/hour ex VAT", "Prices inclusive of VAT",
              "We are VAT registered", "A VAT invoice will be sent"]:
        s = find_signal([("u", t)])
        assert s and s.kind == "registered", t


def test_not_registered_phrases():
    for t in ["We are not VAT registered, so no VAT is added.", "Not currently registered for VAT",
              "VAT not applicable", "We trade below the VAT threshold"]:
        s = find_signal([("u", t)])
        assert s and s.kind == "not_registered", t


def test_no_signal_and_precedence():
    assert find_signal([("u", "Call us today. Company No: 12172366.")]) is None    # Thorcal (real)
    s = find_signal([("a", "Prices plus VAT"), ("b", "We are not VAT registered")])
    assert s.kind == "not_registered" and s.url == "b"

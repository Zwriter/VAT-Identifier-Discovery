"""
UK VAT numbers, company numbers, names and postcodes: parsing, validation, normalisation.

Every rule here comes from a real case seen during research:
  - VAT written with spaces / dots / no GB prefix:  "VAT Reg No: 709 1120 69", "824 5715 26"
  - company numbers with dropped leading zeros:    "Registered in England: 3574049", "No .4955915"
  - non-UK VAT numbers on UK pages:                "VAT IE 4719881IH" (a directory's own footer)
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# --------------------------------------------------------------------------- VAT

WEIGHTS = (8, 7, 6, 5, 4, 3, 2)


def vat_checksum_ok(nine_digits: str) -> bool:
    """HMRC mod-97 check for a 9-digit VAT number (original and post-2010 '+55' series)."""
    if not re.fullmatch(r"\d{9}", nine_digits):
        return False
    total = sum(int(d) * w for d, w in zip(nine_digits[:7], WEIGHTS)) + int(nine_digits[7:])
    return total % 97 == 0 or (total + 55) % 97 == 0


def normalise_vat(raw: str) -> str | None:
    """Return 'GB#########' (or GB + 12-digit branch / GBGD### / GBHA###) if valid, else None."""
    s = re.sub(r"[\s.\-]", "", raw).upper()
    if s.startswith("9932:"):
        s = s[5:]
    if not s.startswith("GB"):
        s = "GB" + s
    m = re.fullmatch(r"GB(\d{9})(\d{3})?", s)
    if m:
        return s if vat_checksum_ok(m.group(1)) else None
    if re.fullmatch(r"GB(GD|HA)\d{3}", s):
        return s
    return None


# A VAT label near the number. Unprefixed digits are only accepted after a label like this.
_VAT_LABEL = r"(?:V\.?\s?A\.?\s?T\.?(?:\s*(?:Reg(?:istration)?\.?|Registered))?(?:\s*(?:No\.?|Number|#))?)"
# 9 digits written as 3-4-2 / 9 straight / with dots, optionally + 3-digit branch
_DIGITS9 = r"(\d{3}[\s.]?\d{4}[\s.]?\d{2}(?:[\s.]?\d{3})?)"

_RE_PREFIXED = re.compile(r"(?<![A-Z0-9])GB[\s.]?" + _DIGITS9 + r"(?!\d)", re.I)
_RE_LABELLED = re.compile(_VAT_LABEL + r"\s*[:.\-]?\s*(?:GB[\s.]?)?" + _DIGITS9 + r"(?!\d)", re.I)


@dataclass
class VatCandidate:
    vat: str            # normalised GB#########
    start: int          # position in text
    end: int
    raw: str            # as written
    labelled: bool      # preceded by a VAT label


def find_vat_candidates(text: str) -> list[VatCandidate]:
    """All checksum-valid GB VAT numbers in text. Non-GB prefixes (IE, DE, ...) are ignored by design."""
    out: dict[tuple[str, int], VatCandidate] = {}
    for rx, rx_labelled in ((_RE_LABELLED, True), (_RE_PREFIXED, False)):
        for m in rx.finditer(text):
            labelled = rx_labelled
            digits = re.sub(r"\D", "", m.group(1))
            before = text[max(0, m.start() - 15): m.start()].upper()
            # EORI for a VAT-registered business = GB + VAT number + 000 -> recover the VAT number
            if len(digits) == 12 and "EORI" in before:
                if not digits.endswith("000"):
                    continue          # VAT-group member or non-VAT EORI: don't guess
                digits = digits[:9]
                labelled = True
            v = normalise_vat(digits)
            if not v:
                continue
            key = (v, m.start(1))
            if key not in out or labelled:
                out[key] = VatCandidate(v, m.start(1), m.end(1), m.group(0).strip(), labelled)
    return sorted(out.values(), key=lambda c: c.start)


# --------------------------------------------------------------- company numbers

def normalise_company_number(raw: str) -> str:
    """Companies House style: 8 characters, 2-letter prefix kept (SC, NI, OC, SO, NC ...)."""
    s = re.sub(r"[\s.]", "", str(raw)).upper()
    m = re.fullmatch(r"([A-Z]{2})?(\d{1,8})", s)
    if not m:
        return s
    prefix, digits = m.group(1) or "", m.group(2)
    return prefix + digits.zfill(8 - len(prefix))


def company_number_variants(number: str) -> list[str]:
    """Forms a company number takes in documents: padded and with leading zeros dropped."""
    n = normalise_company_number(number)
    m = re.fullmatch(r"([A-Z]{2})?(\d+)", n)
    if not m:
        return [n]
    prefix, digits = m.group(1) or "", m.group(2)
    stripped = digits.lstrip("0") or "0"
    variants = {n, prefix + stripped}
    return sorted(variants, key=len, reverse=True)


def find_company_number(text: str, number: str) -> list[int]:
    """Positions where this company's number appears as a standalone token (padded or unpadded)."""
    hits = []
    for v in company_number_variants(number):
        for m in re.finditer(r"(?<![A-Z0-9])" + re.escape(v) + r"(?!\d)", text, re.I):
            hits.append(m.start())
    return sorted(set(hits))


# ------------------------------------------------------------------------ names

_LEGAL = {"LIMITED": "LTD", "COMPANY": "CO", "PUBLIC LIMITED COMPANY": "PLC"}


def normalise_name(name: str) -> str:
    """Uppercase, &->AND, punctuation out, LIMITED->LTD, drop leading THE.
    Distinguishing words such as UK are KEPT (stripping 'UK' caused a false match in testing)."""
    s = name.upper().replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\bPUBLIC LIMITED COMPANY\b", "PLC", s)
    s = re.sub(r"\bLIMITED\b", "LTD", s)
    s = re.sub(r"^THE ", "", s)
    return s


def name_core(name: str) -> str:
    """Name without the legal suffix, for matching 'X LTD' with 'X' (HMRC sometimes omits LTD)."""
    s = normalise_name(name)
    return re.sub(r"\s+(LTD|PLC|LLP|LP|CIC|CO)$", "", s).strip()


def names_match(a: str, b: str) -> bool:
    return bool(a and b) and name_core(a) == name_core(b)


# -------------------------------------------------------------------- postcodes

_RE_POSTCODE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d)([A-Z]{2})\b", re.I)


def postcode_district(pc: str) -> str | None:
    """'GU52 8EA' -> 'GU52 8' (outward code + sector digit). Same business park can have different units."""
    m = _RE_POSTCODE.search(pc or "")
    return f"{m.group(1).upper()} {m.group(2)}" if m else None


def find_postcodes(text: str) -> list[tuple[str, int]]:
    return [(f"{m.group(1).upper()} {m.group(2)}{m.group(3).upper()}", m.start()) for m in _RE_POSTCODE.finditer(text)]

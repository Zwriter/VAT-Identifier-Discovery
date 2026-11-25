"""
Deciding whether a VAT number found in some text belongs to the target company.

Accept only if the number sits next to the target's own identifiers:
  - its company number (padded or unpadded), or
  - its postcode district AND its name.
A VAT number with no such anchor nearby is rejected, however plausible.
(Observed trap: a directory page about LGM Products showed the directory's own
'VAT IE 4719881IH' in its footer.)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import vat as V

WINDOW = 300  # characters either side of the VAT number


@dataclass
class Target:
    company_number: str
    name: str
    postcode: str = ""

    @property
    def district(self) -> str | None:
        return V.postcode_district(self.postcode)


@dataclass
class Decision:
    vat: str
    accepted: bool
    evidence: str            # company_number_adjacent | postcode_name_adjacent | none
    reason: str
    context: str
    position: int
    flags: list[str] = field(default_factory=list)


def _context(text: str, start: int, end: int, pad: int = 150) -> str:
    s = text[max(0, start - pad): min(len(text), end + pad)]
    return " ".join(s.split())


def judge(text: str, target: Target, template_vats: set[str] | None = None) -> list[Decision]:
    """Judge every GB VAT candidate in `text` against `target`."""
    template_vats = template_vats or set()
    num_hits = V.find_company_number(text, target.company_number)
    core = V.name_core(target.name)
    district = target.district
    decisions = []
    for c in V.find_vat_candidates(text):
        lo, hi = c.start - WINDOW, c.end + WINDOW
        window = text[max(0, lo): hi]
        ctx = _context(text, c.start, c.end)
        flags = [] if c.labelled else ["no_vat_label"]

        if c.vat in template_vats:
            decisions.append(Decision(c.vat, False, "none", "site_template_number", ctx, c.start, flags))
            continue
        if any(lo <= p <= hi for p in num_hits):
            decisions.append(Decision(c.vat, True, "company_number_adjacent", "ok", ctx, c.start, flags))
            continue
        pcs_near = {V.postcode_district(p) for p, _ in V.find_postcodes(window)}
        name_near = core and core in V.normalise_name(window)
        if district and district in pcs_near and name_near:
            decisions.append(Decision(c.vat, True, "postcode_name_adjacent", "ok", ctx, c.start, flags))
            continue
        why = "name_only" if name_near else ("postcode_only" if district in pcs_near else "no_anchor")
        decisions.append(Decision(c.vat, False, "none", why, ctx, c.start, flags))
    return decisions


def best(decisions: list[Decision]) -> Decision | None:
    """Pick one accepted number. If two different numbers are accepted, it's ambiguous -> None."""
    acc = [d for d in decisions if d.accepted]
    vats = {d.vat for d in acc}
    if len(vats) != 1:
        return None
    acc.sort(key=lambda d: (d.evidence != "company_number_adjacent", "no_vat_label" in d.flags))
    return acc[0]


def template_numbers(pages_text: list[str], min_pages: int = 2) -> set[str]:
    """VAT numbers repeated on several pages of the same site = header/footer template.
    On a company's own site that's fine (its own footer); on a third-party site it's the publisher's number."""
    seen: dict[str, int] = {}
    for t in pages_text:
        for v in {c.vat for c in V.find_vat_candidates(t)}:
            seen[v] = seen.get(v, 0) + 1
    return {v for v, n in seen.items() if n >= min_pages}

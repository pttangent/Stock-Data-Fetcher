from __future__ import annotations

from dataclasses import dataclass

OWNERSHIP_FORMS = frozenset({"3", "3/A", "4", "4/A", "5", "5/A", "144", "144/A"})

FORM_GROUPS: dict[str, frozenset[str]] = {
    "annual": frozenset({"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}),
    "quarterly": frozenset({"10-Q", "10-Q/A"}),
    "event": frozenset({"8-K", "8-K/A", "6-K", "6-K/A"}),
    "holdings": frozenset({"13F-HR", "13F-HR/A"}),
    "proxy": frozenset({"DEF 14A", "PRE 14A", "DEFA14A", "DEF 14C", "PRE 14C"}),
    "regulatory": frozenset({"SD", "SD/A", "CORRESP", "UPLOAD"}),
    "offering": frozenset({
        "S-1", "S-1/A", "S-3", "S-3/A", "S-3ASR", "S-4", "S-4/A",
        "424B2", "424B3", "424B4", "424B5", "424B7", "424B8", "FWP",
    }),
}

DEFAULT_INCLUDED_FORMS = frozenset().union(*FORM_GROUPS.values()) - OWNERSHIP_FORMS

FORM_PRIORITY = {
    "10-K": 10, "20-F": 11, "40-F": 12,
    "10-Q": 20,
    "8-K": 30, "6-K": 31,
    "13F-HR": 40,
    "DEF 14A": 50, "PRE 14A": 51, "DEFA14A": 52,
    "SD": 60, "CORRESP": 61, "UPLOAD": 62,
    "S-1": 70, "S-3": 71, "S-3ASR": 72, "S-4": 73,
    "424B2": 74, "424B3": 75, "424B4": 76, "424B5": 77,
    "424B7": 78, "424B8": 79, "FWP": 80,
}

PARSE_TASK_BY_GROUP = {
    "annual": "parse_annual",
    "quarterly": "parse_quarterly",
    "event": "parse_event",
    "holdings": "parse_holdings",
    "proxy": "parse_proxy",
    "regulatory": "parse_regulatory",
    "offering": "parse_offering",
}

SEMANTIC_TASK_BY_GROUP = {
    "annual": "semantic_annual",
    "quarterly": "semantic_quarterly",
    "event": "semantic_event",
    "holdings": "semantic_holdings",
    "proxy": "semantic_proxy",
    "regulatory": "semantic_regulatory",
    "offering": "semantic_offering",
}

LANE_BY_TASK = {
    "discover_company": "download",
    "download_filing": "download",
    "fetch_yahoo": "yahoo",
    "import_archive": "download",
    "parse_annual": "parse_core",
    "parse_quarterly": "parse_core",
    "parse_event": "parse_event",
    "parse_holdings": "parse_holdings",
    "parse_proxy": "parse_other",
    "parse_regulatory": "parse_other",
    "parse_offering": "parse_other",
    "semantic_annual": "semantic_core",
    "semantic_quarterly": "semantic_core",
    "semantic_event": "semantic_event",
    "semantic_holdings": "semantic_holdings",
    "semantic_proxy": "semantic_other",
    "semantic_regulatory": "semantic_other",
    "semantic_offering": "semantic_other",
    "finalize_symbol": "finalize",
}


def base_form(form: str) -> str:
    value = (form or "").strip().upper()
    return value[:-2] if value.endswith("/A") else value


def form_group(form: str) -> str | None:
    value = (form or "").strip().upper()
    for group, forms in FORM_GROUPS.items():
        if value in forms:
            return group
    return None


def form_priority(form: str) -> int:
    return FORM_PRIORITY.get(base_form(form), 999)


@dataclass(frozen=True)
class FormPolicy:
    include_forms: frozenset[str] = DEFAULT_INCLUDED_FORMS
    exclude_forms: frozenset[str] = OWNERSHIP_FORMS

    def allows(self, form: str) -> bool:
        value = (form or "").strip().upper()
        if value in self.exclude_forms or base_form(value) in {base_form(x) for x in self.exclude_forms}:
            return False
        return value in self.include_forms or base_form(value) in {base_form(x) for x in self.include_forms}

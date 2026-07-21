from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CikMatch:
    cik: str
    symbol: str
    title: str | None = None


@dataclass(frozen=True)
class FilingMetadata:
    cik: str
    company_name: str | None
    form: str
    filing_date: str
    accepted_at: str | None
    report_period: str | None
    accession_number: str
    primary_document: str
    source_url: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FilingContent:
    metadata: FilingMetadata
    text: str
    html: str | None
    retrieval_method: str


@dataclass(frozen=True)
class FilingSection:
    key: str
    title: str
    text: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class YahooProfile:
    requested_symbol: str
    yahoo_symbol: str
    observed_at: str
    payload: dict[str, Any]

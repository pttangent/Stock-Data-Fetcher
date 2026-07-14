from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import asdict
from html import unescape
from pathlib import Path
from typing import Any

from ..config import Settings
from ..models import CikMatch, FilingContent, FilingMetadata, FilingSection
from ..util import (
    RateLimiter,
    atomic_write,
    canonical_json,
    file_is_fresh,
    retry_delays,
    sec_symbol_candidates,
    sha256_bytes,
    utc_now,
)

ANNUAL_FORM_PRIORITY = ("10-K", "20-F", "40-F")
SECTION_EXTRACTOR_VERSION = "regex-items-v1"


class SecRequestError(RuntimeError):
    pass


class SecHttpClient:
    def __init__(
        self,
        identity: str,
        *,
        requests_per_second: float = 5.0,
        max_attempts: int = 5,
        opener: Callable[[urllib.request.Request, float], bytes] | None = None,
    ):
        self.identity = identity
        self.max_attempts = max_attempts
        self.limiter = RateLimiter(requests_per_second=requests_per_second)
        self._opener = opener or self._default_open

    @staticmethod
    def _default_open(request: urllib.request.Request, timeout: float) -> bytes:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.read()

    def get_bytes(self, url: str, timeout: float = 60.0) -> bytes:
        delays = retry_delays(self.max_attempts)
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            self.limiter.wait()
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": self.identity,
                    "Accept": "application/json,text/html,application/xhtml+xml,*/*",
                },
            )
            try:
                return self._opener(request, timeout)
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in {403, 408, 429, 500, 502, 503, 504}:
                    raise SecRequestError(f"SEC HTTP {exc.code}: {url}") from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
            if attempt < self.max_attempts:
                time.sleep(delays[attempt - 1])
        raise SecRequestError(
            f"SEC request failed after {self.max_attempts} attempts: {url}"
        ) from last_error

    def get_json(self, url: str) -> dict[str, Any]:
        return json.loads(self.get_bytes(url).decode("utf-8"))


class EdgarToolsAdapter:
    """Small compatibility wrapper around EdgarTools, loaded lazily."""

    def __init__(self, identity: str):
        self.identity = identity

    def fetch_text(self, symbol: str, metadata: FilingMetadata) -> str:
        try:
            from edgar import Company, set_identity
        except ImportError as exc:  # pragma: no cover - dependency path
            raise RuntimeError("edgartools is not installed") from exc

        set_identity(self.identity)
        company = Company(symbol)
        filings = company.get_filings(form=metadata.form)
        candidates = []
        try:
            candidates = list(filings)
        except TypeError:
            candidates = [filings[index] for index in range(len(filings))]
        selected = None
        for filing in candidates:
            accession = str(getattr(filing, "accession_number", ""))
            form = str(getattr(filing, "form", ""))
            if accession == metadata.accession_number and form == metadata.form:
                selected = filing
                break
        if selected is None:
            raise LookupError(
                "EdgarTools did not return "
                f"{metadata.form} {metadata.accession_number} for {symbol}"
            )
        text = selected.text()
        if not isinstance(text, str) or len(text.strip()) < 100:
            raise ValueError("EdgarTools returned empty filing text")
        return text


class SecProvider:
    def __init__(
        self,
        settings: Settings,
        *,
        http_client: SecHttpClient | None = None,
        edgar_adapter: EdgarToolsAdapter | None = None,
    ):
        settings.validate_sec_identity()
        self.settings = settings
        self.http = http_client or SecHttpClient(
            settings.sec_identity or "",
            requests_per_second=settings.sec_requests_per_second,
            max_attempts=settings.sec_max_attempts,
        )
        self.edgar = edgar_adapter or EdgarToolsAdapter(settings.sec_identity or "")
        self.cache_dir = settings.cache_dir / "sec"
        self.raw_dir = settings.raw_dir / "sec"
        self._ticker_map: dict[str, CikMatch] | None = None

    def load_ticker_map(self, *, refresh: bool = False) -> dict[str, CikMatch]:
        path = self.cache_dir / "company_tickers.json"
        if refresh or not file_is_fresh(path, self.settings.sec_cache_ttl_hours):
            payload = self.http.get_bytes("https://www.sec.gov/files/company_tickers.json")
            atomic_write(path, payload)
        raw = json.loads(path.read_text(encoding="utf-8"))
        result: dict[str, CikMatch] = {}
        rows = raw.values() if isinstance(raw, dict) else raw
        for row in rows:
            ticker = str(row.get("ticker", "")).upper()
            if not ticker:
                continue
            match = CikMatch(
                cik=str(row["cik_str"]).zfill(10), symbol=ticker, title=row.get("title")
            )
            for candidate in sec_symbol_candidates(ticker):
                result[candidate] = match
        self._ticker_map = result
        return result

    def lookup_cik(self, symbol: str) -> CikMatch | None:
        mapping = self._ticker_map or self.load_ticker_map()
        for candidate in sec_symbol_candidates(symbol):
            if candidate in mapping:
                return mapping[candidate]
        return None

    def bootstrap_bulk_submissions(self, *, refresh: bool = False) -> Path:
        """Download and extract the SEC nightly submissions bulk archive."""
        archive = self.cache_dir / "submissions.zip"
        target = self.cache_dir / "submissions"
        marker = target / ".bulk_complete"
        if marker.exists() and not refresh:
            return target
        payload = self.http.get_bytes(
            "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip",
            timeout=300.0,
        )
        atomic_write(archive, payload)
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                name = Path(member.filename).name
                if not name.startswith("CIK") or not name.endswith(".json"):
                    continue
                atomic_write(target / name, bundle.read(member))
        atomic_write(marker, utc_now().encode("utf-8"))
        return target

    def get_submissions(self, cik: str, *, refresh: bool = False) -> dict[str, Any]:
        cik = str(cik).zfill(10)
        path = self.cache_dir / "submissions" / f"CIK{cik}.json"
        if refresh or not file_is_fresh(path, self.settings.sec_cache_ttl_hours):
            payload = self.http.get_bytes(f"https://data.sec.gov/submissions/CIK{cik}.json")
            atomic_write(path, payload)
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def select_latest_annual_filing(submissions: dict[str, Any]) -> FilingMetadata | None:
        recent = submissions.get("filings", {}).get("recent", {})
        if not recent:
            return None
        columns = [
            "accessionNumber",
            "filingDate",
            "acceptanceDateTime",
            "reportDate",
            "form",
            "primaryDocument",
        ]
        lengths = [len(recent.get(name, [])) for name in columns]
        if not lengths or min(lengths) == 0:
            return None
        company_name = submissions.get("name")
        cik = str(submissions.get("cik", "")).zfill(10)
        rows: list[dict[str, Any]] = []
        for index in range(min(lengths)):
            row = {name: recent[name][index] for name in columns}
            # Exact annual forms only; never promote amendments such as 10-K/A.
            if row["form"] in ANNUAL_FORM_PRIORITY:
                rows.append(row)
        if not rows:
            return None
        rows.sort(
            key=lambda row: (row.get("filingDate") or "", row.get("acceptanceDateTime") or ""),
            reverse=True,
        )
        row = rows[0]
        accession = row["accessionNumber"]
        primary = row["primaryDocument"]
        cik_int = str(int(cik)) if cik else ""
        source_url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
            f"{accession.replace('-', '')}/{primary}"
        )
        return FilingMetadata(
            cik=cik,
            company_name=company_name,
            form=row["form"],
            filing_date=row["filingDate"],
            accepted_at=row.get("acceptanceDateTime") or None,
            report_period=row.get("reportDate") or None,
            accession_number=accession,
            primary_document=primary,
            source_url=source_url,
            raw=row,
        )

    def fetch_latest_annual_filing(
        self, symbol: str
    ) -> tuple[dict[str, Any], FilingMetadata] | None:
        match = self.lookup_cik(symbol)
        if match is None:
            return None
        submissions = self.get_submissions(match.cik)
        metadata = self.select_latest_annual_filing(submissions)
        if metadata is None:
            return None
        return submissions, metadata

    def fetch_filing_content(self, symbol: str, metadata: FilingMetadata) -> FilingContent:
        errors: list[str] = []
        try:
            text = self.edgar.fetch_text(symbol, metadata)
            return FilingContent(metadata, text=text, html=None, retrieval_method="edgartools")
        except Exception as exc:  # fallback is intentional
            errors.append(f"edgartools: {type(exc).__name__}: {exc}")

        try:
            content = self.http.get_bytes(metadata.source_url)
            html = content.decode("utf-8", errors="replace")
            text = html_to_text(html)
            if len(text.strip()) < 100:
                raise ValueError("SEC archive document converted to empty text")
            return FilingContent(metadata, text=text, html=html, retrieval_method="sec_archive")
        except Exception as exc:
            errors.append(f"sec_archive: {type(exc).__name__}: {exc}")
        raise RuntimeError("; ".join(errors))

    def persist_filing(self, content: FilingContent) -> tuple[Path, str, str]:
        accession = content.metadata.accession_number
        folder = self.raw_dir / content.metadata.cik / accession
        text_path = folder / "filing.txt"
        atomic_write(text_path, content.text.encode("utf-8"))
        if content.html is not None:
            atomic_write(folder / content.metadata.primary_document, content.html.encode("utf-8"))
        metadata_path = folder / "metadata.json"
        metadata_payload = {
            **asdict(content.metadata),
            "retrieved_at": utc_now(),
            "retrieval_method": content.retrieval_method,
        }
        atomic_write(metadata_path, canonical_json(metadata_payload).encode("utf-8"))
        return text_path, sha256_bytes(content.text.encode("utf-8")), "text/plain"


def html_to_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n")
    except ImportError:  # pragma: no cover - dependency path
        text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text).replace("\xa0", " ")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


_HEADING_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("business", "Item 1. Business", re.compile(r"(?im)^item\s+1[.\s:-]+business\b")),
    (
        "risk_factors",
        "Item 1A. Risk Factors",
        re.compile(r"(?im)^item\s+1a[.\s:-]+risk\s+factors\b"),
    ),
    (
        "properties",
        "Item 2. Properties",
        re.compile(r"(?im)^item\s+2[.\s:-]+properties\b"),
    ),
    (
        "mda",
        "Item 7. Management's Discussion and Analysis",
        re.compile(r"(?im)^item\s+7[.\s:-]+management['’]?s\s+discussion"),
    ),
    (
        "financial_statements",
        "Item 8. Financial Statements",
        re.compile(r"(?im)^item\s+8[.\s:-]+financial\s+statements"),
    ),
    (
        "information_on_company",
        "Item 4. Information on the Company",
        re.compile(r"(?im)^item\s+4[.\s:-]+information\s+on\s+the\s+company\b"),
    ),
]


def extract_sections(text: str) -> list[FilingSection]:
    """Extract deterministic filing sections while retaining exact character offsets."""
    if not text:
        return []
    found: list[tuple[int, str, str]] = []
    for key, title, pattern in _HEADING_PATTERNS:
        matches = list(pattern.finditer(text))
        if matches:
            # TOCs usually occur near the beginning. The last useful heading is often the body.
            preferred = next(
                (m for m in matches if m.start() > min(5000, len(text) // 20)), matches[-1]
            )
            found.append((preferred.start(), key, title))
    found.sort()
    sections = [FilingSection("full_text", "Full filing text", text, 0, len(text))]
    for index, (start, key, title) in enumerate(found):
        end = found[index + 1][0] if index + 1 < len(found) else len(text)
        chunk = text[start:end].strip()
        if len(chunk) >= 20:
            actual_start = text.find(chunk, start, end)
            sections.append(
                FilingSection(key, title, chunk, actual_start, actual_start + len(chunk))
            )
    return sections

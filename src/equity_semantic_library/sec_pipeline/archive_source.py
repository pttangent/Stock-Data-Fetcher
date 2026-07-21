from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import threading
import time
from typing import Any
import urllib.error
import urllib.request
from zipfile import ZipFile

from .config import PipelineConfig
from .forms import FormPolicy
from .store import canonical_json, utc_now


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_symbol(value: str) -> str:
    return value.strip().upper().replace("/", ".")


def _scalar(value: Any) -> Any:
    if value is None:
        return None
    try:
        if value != value:
            return None
    except Exception:
        pass
    return value.item() if hasattr(value, "item") else value


def load_symbol_metadata(path: str | Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Read source metadata without mutating it; return market-cap-descending equities."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError("Parquet input requires pip install '.[parquet]'") from exc
        records = pd.read_parquet(path).to_dict(orient="records")
    elif suffix == ".csv":
        import csv
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            records = list(csv.DictReader(handle))
    else:
        raise ValueError(f"Unsupported symbol metadata: {path.suffix}")
    rows: list[dict[str, Any]] = []
    for raw in records:
        lower = {str(k).lower(): _scalar(v) for k, v in raw.items()}
        symbol = normalize_symbol(str(lower.get("symbol") or lower.get("ticker") or ""))
        if not symbol:
            continue
        is_etf = lower.get("is_etf")
        if isinstance(is_etf, str):
            is_etf = is_etf.strip().lower() in {"1", "true", "yes", "y"}
        quote_type = str(lower.get("quote_type") or "").upper()
        security_type = str(lower.get("security_type") or "").upper()
        if is_etf or quote_type in {"ETF", "MUTUALFUND", "INDEX"} or security_type == "ETF":
            continue
        market_cap = lower.get("market_cap")
        rank = lower.get("rank")
        try:
            market_cap = float(market_cap) if market_cap not in (None, "") else None
        except (TypeError, ValueError):
            market_cap = None
        try:
            rank = int(float(rank)) if rank not in (None, "") else None
        except (TypeError, ValueError):
            rank = None
        normalized = {
            "symbol": symbol,
            "source_symbol": str(lower.get("source_symbol") or symbol),
            "company_name": lower.get("company_name"),
            "sector_code": lower.get("sector_code"),
            "industry_code": lower.get("industry_code"),
            "market_cap": market_cap,
            "rank": rank,
            "exchange": lower.get("exchange"),
            "country": lower.get("country"),
            "quote_type": lower.get("quote_type"),
            "security_type": lower.get("security_type"),
            "is_etf": 1 if is_etf else 0,
            "source_path": str(path.resolve()),
        }
        normalized["source_row_hash"] = sha256_bytes(canonical_json(normalized).encode("utf-8"))
        rows.append(normalized)
    rows.sort(key=lambda r: (-(r["market_cap"] or -1), r["rank"] if r["rank"] is not None else 10**12, r["symbol"]))
    return rows[:limit] if limit else rows


class GlobalRateGate:
    """Thread-safe request-start pacing shared by every SEC download worker."""
    def __init__(self, requests_per_second: float):
        if not 0 < requests_per_second <= 10:
            raise ValueError("SEC requests_per_second must be in (0, 10]")
        self.interval = 1.0 / requests_per_second
        self.lock = threading.Lock()
        self.next_at = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_at - now)
            self.next_at = max(now, self.next_at) + self.interval
        if delay:
            time.sleep(delay)


class SecClient:
    def __init__(self, config: PipelineConfig, gate: GlobalRateGate | None = None):
        config.validate(require_sec=True)
        self.config = config
        self.gate = gate or GlobalRateGate(config.sec_requests_per_second)

    def get_bytes(self, url: str, *, timeout: float | None = None) -> tuple[bytes, dict[str, Any]]:
        timeout = timeout or self.config.sec_request_timeout_seconds
        last: Exception | None = None
        for attempt in range(1, self.config.sec_max_attempts + 1):
            self.gate.wait()
            request = urllib.request.Request(url, headers={
                "User-Agent": self.config.sec_identity or "",
                "Accept": "application/json,text/html,text/plain,application/xml,*/*",
                "Accept-Encoding": "gzip, deflate",
            })
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                    payload = response.read(self.config.max_document_bytes + 1)
                    if len(payload) > self.config.max_document_bytes:
                        raise ValueError(f"SEC payload exceeds max_document_bytes: {url}")
                    return payload, {
                        "url": url, "status": getattr(response, "status", 200),
                        "content_type": response.headers.get("content-type"),
                        "etag": response.headers.get("etag"),
                        "last_modified": response.headers.get("last-modified"),
                        "fetched_at": utc_now(),
                    }
            except urllib.error.HTTPError as exc:
                last = exc
                if exc.code not in {403, 408, 429, 500, 502, 503, 504}:
                    raise
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = exc
            if attempt < self.config.sec_max_attempts:
                time.sleep(min(30.0, 2 ** (attempt - 1)) + 0.05 * attempt)
        raise RuntimeError(f"SEC request failed: {url}: {last}") from last

    def get_json(self, url: str) -> dict[str, Any]:
        payload, _ = self.get_bytes(url)
        return json.loads(payload.decode("utf-8"))


class SecArchive:
    TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
    SUBMISSIONS_URL = "https://data.sec.gov/submissions"
    ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"

    def __init__(self, config: PipelineConfig, client: SecClient):
        self.config = config
        self.client = client
        self.cache_dir = config.cache_dir / "sec"
        self.raw_dir = config.raw_dir / "sec"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self._ticker_map: dict[str, dict[str, Any]] | None = None

    def ticker_map(self, refresh: bool = False) -> dict[str, dict[str, Any]]:
        path = self.cache_dir / "company_tickers.json"
        if refresh or not path.exists():
            payload, meta = self.client.get_bytes(self.TICKER_MAP_URL)
            atomic_write(path, payload)
            atomic_write(path.with_suffix(".evidence.json"), canonical_json(meta).encode())
        raw = json.loads(path.read_text(encoding="utf-8"))
        out: dict[str, dict[str, Any]] = {}
        rows = raw.values() if isinstance(raw, dict) else raw
        for row in rows:
            symbol = normalize_symbol(str(row.get("ticker") or ""))
            if symbol:
                out[symbol] = {"cik": str(row["cik_str"]).zfill(10), "title": row.get("title")}
                out[symbol.replace(".", "-")] = out[symbol]
        self._ticker_map = out
        return out

    def lookup(self, symbol: str) -> dict[str, Any] | None:
        mapping = self._ticker_map or self.ticker_map()
        symbol = normalize_symbol(symbol)
        return mapping.get(symbol) or mapping.get(symbol.replace(".", "-"))

    def submissions(self, cik: str, refresh: bool = False) -> dict[str, Any]:
        cik = str(cik).zfill(10)
        path = self.cache_dir / "submissions" / f"CIK{cik}.json"
        if refresh or not path.exists():
            payload, meta = self.client.get_bytes(f"{self.SUBMISSIONS_URL}/CIK{cik}.json")
            atomic_write(path, payload)
            atomic_write(path.with_suffix(".evidence.json"), canonical_json(meta).encode())
        return json.loads(path.read_text(encoding="utf-8"))

    def discover_filings(self, cik: str, policy: FormPolicy, *, refresh: bool = False, from_date: str | None = None, to_date: str | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        root = self.submissions(cik, refresh=refresh)
        filing_root = root.get("filings") or {}
        shards: list[tuple[str, dict[str, Any]]] = [("recent", filing_root.get("recent") or {})]
        shard_dir = self.cache_dir / "submissions" / f"CIK{str(cik).zfill(10)}"
        for descriptor in filing_root.get("files") or []:
            name = descriptor.get("name")
            if not name:
                continue
            path = shard_dir / PurePosixPath(name).name
            if refresh or not path.exists():
                payload, meta = self.client.get_bytes(f"{self.SUBMISSIONS_URL}/{name}")
                atomic_write(path, payload)
                atomic_write(path.with_suffix(".evidence.json"), canonical_json(meta).encode())
            shards.append((name, json.loads(path.read_text(encoding="utf-8"))))
        keys = ["accessionNumber", "filingDate", "reportDate", "acceptanceDateTime", "form", "primaryDocument", "primaryDocDescription", "items", "size", "isXBRL", "isInlineXBRL"]
        found: dict[str, dict[str, Any]] = {}
        for shard_name, columns in shards:
            accessions = columns.get("accessionNumber") or []
            for index, accession in enumerate(accessions):
                row = {key: (columns.get(key) or [None] * len(accessions))[index] if index < len(columns.get(key) or []) else None for key in keys}
                form = str(row.get("form") or "").upper()
                date = row.get("filingDate") or ""
                if not policy.allows(form) or (from_date and date and date < from_date) or (to_date and date and date > to_date):
                    continue
                row["sourceShard"] = shard_name
                found[str(accession)] = row
        rows = sorted(found.values(), key=lambda r: (r.get("filingDate") or "", r.get("acceptanceDateTime") or "", r.get("accessionNumber") or ""), reverse=True)
        return root, rows

    def urls(self, cik: str, filing: dict[str, Any]) -> dict[str, str | None]:
        accession = str(filing["accessionNumber"])
        directory = f"{self.ARCHIVES_URL}/{int(str(cik))}/{accession.replace('-', '')}"
        primary = filing.get("primaryDocument")
        return {
            "complete": f"{self.ARCHIVES_URL}/{int(str(cik))}/{accession}.txt",
            "fallback": f"{directory}/{accession}.txt",
            "primary": f"{directory}/{primary}" if primary else None,
            "index": f"{directory}/{accession}-index.html",
        }

    def download_complete(self, symbol: str, cik: str, filing: dict[str, Any]) -> dict[str, Any]:
        accession = str(filing["accessionNumber"])
        target_dir = self.raw_dir / f"ticker={symbol}" / f"cik={str(cik).zfill(10)}" / f"accession={accession}"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / ("complete-submission.txt.gz" if self.config.compress_raw else "complete-submission.txt")
        evidence_path = target_dir / "evidence.json"
        if target.exists() and evidence_path.exists():
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            return {**evidence, "status": "skipped", "storage_uri": str(target.resolve())}
        urls = self.urls(cik, filing)
        try:
            payload, response = self.client.get_bytes(str(urls["complete"]))
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            payload, response = self.client.get_bytes(str(urls["fallback"]))
        source_hash = sha256_bytes(payload)
        if self.config.compress_raw:
            tmp = target.with_suffix(target.suffix + ".part")
            with gzip.open(tmp, "wb", compresslevel=6) as handle:
                handle.write(payload)
            os.replace(tmp, target)
        else:
            atomic_write(target, payload)
        evidence = {
            **response, "symbol": symbol, "cik": str(cik).zfill(10), "accession": accession,
            "form": str(filing.get("form") or ""), "filing_date": filing.get("filingDate"),
            "report_date": filing.get("reportDate"), "accepted_at": filing.get("acceptanceDateTime"),
            "sha256": source_hash, "bytes": len(payload), "compressed_bytes": target.stat().st_size,
            "storage_uri": str(target.resolve()),
        }
        atomic_write(evidence_path, canonical_json(evidence).encode("utf-8"))
        return {**evidence, "status": "downloaded"}


def atomic_write(path: str | Path, payload: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(payload)
    os.replace(tmp, path)


def read_storage_uri(uri: str) -> bytes:
    if uri.startswith("zip://"):
        archive, member = uri[6:].split("!", 1)
        with ZipFile(archive) as bundle:
            return bundle.read(member)
    path = Path(uri)
    if path.suffix.lower() == ".gz":
        with gzip.open(path, "rb") as handle:
            return handle.read()
    return path.read_bytes()


def inventory_archive(path: str | Path, policy: FormPolicy) -> list[dict[str, Any]]:
    """Inventory a previously downloaded ticker ZIP without extracting it."""
    path = Path(path).resolve()
    rows: list[dict[str, Any]] = []
    with ZipFile(path) as bundle:
        names = set(bundle.namelist())
        for name in sorted(n for n in names if n.endswith("/filing.json")):
            metadata = json.loads(bundle.read(name).decode("utf-8"))
            form = str(metadata.get("form") or "").upper()
            if not policy.allows(form):
                continue
            base = name.rsplit("/", 1)[0]
            raw_member = base + "/complete-submission.txt"
            if raw_member not in names:
                continue
            evidence_member = raw_member + ".evidence.json"
            expected_sha = None
            if evidence_member in names:
                try:
                    expected_sha = json.loads(bundle.read(evidence_member).decode("utf-8")).get("sha256")
                except Exception:
                    pass
            rows.append({
                "metadata": metadata,
                "storage_uri": f"zip://{path}!{raw_member}",
                "expected_sha256": expected_sha,
                "source_archive": str(path),
            })
    return rows

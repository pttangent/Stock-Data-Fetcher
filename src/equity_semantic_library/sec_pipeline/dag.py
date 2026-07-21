from __future__ import annotations

from collections.abc import Callable
import hashlib
import re
import threading
import time
from pathlib import Path
from typing import Any

from .archive import GlobalRateGate, SecArchive, SecClient, inventory_archive, load_symbol_metadata, sha256_file
from .config import PipelineConfig
from .dag_workers import DagWorkerMixin
from .forms import LANE_BY_TASK, PARSE_TASK_BY_GROUP, FormPolicy, base_form, form_group, form_priority
from .store import PipelineStore, stable_id, utc_now


class YahooGate:
    def __init__(self, interval: float):
        self.interval = max(0.0, interval)
        self.lock = threading.Lock()
        self.next_at = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_at - now)
            self.next_at = max(now, self.next_at) + self.interval
        if delay:
            time.sleep(delay)


class DagPipeline(DagWorkerMixin):
    def __init__(self, config: PipelineConfig, *, store: PipelineStore | None = None):
        self.config = config
        self.store = store or PipelineStore(config.db_path)
        self.store.initialize()
        self.policy = FormPolicy(config.include_forms, config.exclude_forms)
        self.sec_gate = GlobalRateGate(config.sec_requests_per_second)
        self.sec_client: SecClient | None = None
        self.sec_archive: SecArchive | None = None
        self.yahoo_gate = YahooGate(config.yahoo_min_interval_seconds)
        self.stop_event = threading.Event()
        self.handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any] | None]] = {
            "discover_company": self._discover_company,
            "download_filing": self._download_filing,
            "fetch_yahoo": self._fetch_yahoo,
            "parse_annual": self._parse_filing,
            "parse_quarterly": self._parse_filing,
            "parse_event": self._parse_filing,
            "parse_holdings": self._parse_filing,
            "parse_proxy": self._parse_filing,
            "parse_regulatory": self._parse_filing,
            "parse_offering": self._parse_filing,
            "semantic_annual": self._semantic_filing,
            "semantic_quarterly": self._semantic_filing,
            "semantic_event": self._semantic_filing,
            "semantic_holdings": self._semantic_filing,
            "semantic_proxy": self._semantic_filing,
            "semantic_regulatory": self._semantic_filing,
            "semantic_offering": self._semantic_filing,
            "finalize_symbol": self._finalize_symbol,
        }

    def _ensure_sec(self) -> SecArchive:
        if self.sec_archive is None:
            self.config.validate(require_sec=True)
            self.sec_client = SecClient(self.config, self.sec_gate)
            self.sec_archive = SecArchive(self.config, self.sec_client)
        return self.sec_archive

    def create_online_run(self, *, metadata_path: str | Path | None = None, limit: int | None = None, refresh: bool = False, use_yahoo: bool = True) -> str:
        path = Path(metadata_path or self.config.symbol_metadata_path)
        rows = load_symbol_metadata(path, limit=limit)
        source_hash = sha256_file(path)
        self.store.upsert_universe_rows(rows)
        run_id = self.store.start_run(self.config.to_jsonable(), str(path.resolve()), source_hash)
        for index, row in enumerate(rows):
            priority = index * 1000
            discover = self.store.schedule_task(
                run_id=run_id, task_type="discover_company", lane="download", priority=priority,
                symbol=row["symbol"], payload={"refresh": refresh, "market_cap": row.get("market_cap"), "rank": row.get("rank")},
                max_attempts=self.config.task_max_attempts,
            )
            if use_yahoo:
                self.store.schedule_task(
                    run_id=run_id, task_type="fetch_yahoo", lane="yahoo", priority=priority + 1,
                    symbol=row["symbol"], payload={"refresh": refresh}, max_attempts=self.config.task_max_attempts,
                    dependencies=[discover],
                )
            self.store.schedule_task(
                run_id=run_id, task_type="finalize_symbol", lane="finalize", priority=priority + 999,
                symbol=row["symbol"], dependencies=[discover], max_attempts=1,
            )
        return run_id

    def create_archive_run(self, archives: list[str | Path], *, symbol: str | None = None) -> str:
        source_hash = hashlib.sha256()
        paths = [Path(p).resolve() for p in archives]
        for path in paths:
            source_hash.update(path.as_posix().encode())
            source_hash.update(sha256_file(path).encode())
        run_id = self.store.start_run(self.config.to_jsonable(), ";".join(map(str, paths)), source_hash.hexdigest())
        for archive_index, path in enumerate(paths):
            rows = inventory_archive(path, self.policy)
            for filing_index, item in enumerate(rows):
                metadata = item["metadata"]
                filing_symbol = str(metadata.get("ticker") or symbol or _ticker_from_path(path)).upper()
                cik = str(metadata.get("cik") or "").zfill(10)
                if not cik.strip("0"):
                    cik = f"offline-{stable_id(filing_symbol)[:10]}"
                issuer_id, security_id = self.store.upsert_identity(
                    symbol=filing_symbol, cik=cik, legal_name=metadata.get("companyName"), metadata=metadata
                )
                form = str(metadata.get("form") or "").upper()
                group = form_group(form)
                if not group:
                    continue
                accession = str(metadata.get("accessionNumber") or _accession_from_uri(item["storage_uri"]))
                available_at = metadata.get("acceptanceDateTime") or metadata.get("filingDate") or utc_now()
                precision = "datetime" if metadata.get("acceptanceDateTime") else "date"
                filing_id = self.store.upsert_filing({
                    "issuer_id": issuer_id, "security_id": security_id, "symbol": filing_symbol, "cik": cik,
                    "accession": accession, "form": form, "base_form": base_form(form), "form_group": group,
                    "filing_date": metadata.get("filingDate"), "report_date": metadata.get("reportDate"),
                    "accepted_at": metadata.get("acceptanceDateTime"), "available_at": available_at,
                    "available_at_precision": precision, "primary_document": metadata.get("primaryDocument"),
                    "source_url": metadata.get("completeSubmissionUrl") or metadata.get("filingIndexUrl") or str(path),
                    "raw_storage_uri": item["storage_uri"], "raw_sha256": item.get("expected_sha256"),
                    "raw_bytes": None, "compressed_bytes": path.stat().st_size,
                    "retrieved_at": metadata.get("updatedAt") or utc_now(), "status": "downloaded",
                    "metadata": {**metadata, "source_archive": str(path), "expected_sha256": item.get("expected_sha256")},
                })
                parse_task = PARSE_TASK_BY_GROUP[group]
                priority = archive_index * 1_000_000 + filing_index * 1000 + form_priority(form)
                self.store.schedule_task(
                    run_id=run_id, task_type=parse_task, lane=LANE_BY_TASK[parse_task], priority=priority,
                    symbol=filing_symbol, cik=cik, accession=accession, form=form,
                    payload={"filing_id": filing_id, "expected_sha256": item.get("expected_sha256")},
                    max_attempts=self.config.task_max_attempts,
                )
        return run_id

    def run(self, run_id: str) -> dict[str, Any]:
        self.stop_event.clear()
        threads: list[threading.Thread] = []
        for lane, count in self.config.workers.as_dict().items():
            for index in range(count):
                worker_id = f"{lane}-{index + 1}"
                thread = threading.Thread(target=self._worker_loop, args=(run_id, lane, worker_id), daemon=True)
                thread.start()
                threads.append(thread)
        while self.store.pending_count(run_id) > 0:
            self.store.cancel_blocked_tasks(run_id)
            time.sleep(self.config.scheduler_poll_seconds)
        self.stop_event.set()
        for thread in threads:
            thread.join(timeout=5)
        return self.store.finish_run(run_id)

    def _worker_loop(self, run_id: str, lane: str, worker_id: str) -> None:
        while not self.stop_event.is_set():
            task = self.store.claim_task(run_id=run_id, lane=lane, worker_id=worker_id, lease_seconds=self.config.task_lease_seconds)
            if task is None:
                if self.store.pending_count(run_id) == 0:
                    return
                time.sleep(self.config.scheduler_poll_seconds)
                continue
            try:
                result = self.handlers[task["task_type"]](task) or {}
                self.store.complete_task(task["task_id"], worker_id, result)
            except Exception as exc:
                self.store.fail_task(task, worker_id, exc)


def _ticker_from_path(path: Path) -> str:
    match = re.search(r"ticker=([A-Za-z0-9.\-]+)", path.name)
    return match.group(1).upper() if match else path.stem.upper()


def _accession_from_uri(uri: str) -> str:
    match = re.search(r"accession=([^/!]+)", uri)
    return match.group(1) if match else stable_id(uri)

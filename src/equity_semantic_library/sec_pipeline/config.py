from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .forms import DEFAULT_INCLUDED_FORMS, OWNERSHIP_FORMS


@dataclass(frozen=True)
class WorkerConfig:
    download: int = 4
    yahoo: int = 2
    parse_core: int = 4
    parse_event: int = 3
    parse_holdings: int = 2
    parse_other: int = 3
    semantic_core: int = 4
    semantic_event: int = 3
    semantic_holdings: int = 2
    semantic_other: int = 3
    finalize: int = 1

    def as_dict(self) -> dict[str, int]:
        return {k: int(v) for k, v in asdict(self).items() if int(v) > 0}


@dataclass(frozen=True)
class PipelineConfig:
    db_path: Path = Path("data/sec_yfinance_structured.db")
    data_dir: Path = Path("data/sec_yfinance")
    symbol_metadata_path: Path = Path(
        r"D:\DEV\AnotherNetworkFactory\RAW_DATA\metadata\symbol_metadata.parquet"
    )
    sec_identity: str | None = None
    sec_requests_per_second: float = 4.0
    sec_max_attempts: int = 6
    sec_request_timeout_seconds: float = 90.0
    yahoo_min_interval_seconds: float = 0.75
    yahoo_max_attempts: int = 4
    include_forms: frozenset[str] = DEFAULT_INCLUDED_FORMS
    exclude_forms: frozenset[str] = OWNERSHIP_FORMS
    from_date: str | None = None
    to_date: str | None = None
    compress_raw: bool = True
    keep_complete_submission: bool = True
    keep_split_attachments: bool = False
    max_document_bytes: int = 512 * 1024 * 1024
    evidence_max_chars: int = 800
    xbrl_mode: str = "key_facts"
    workers: WorkerConfig = field(default_factory=WorkerConfig)
    task_max_attempts: int = 3
    task_lease_seconds: int = 900
    scheduler_poll_seconds: float = 0.2
    stop_free_gb: float = 8.0
    disk_safety_margin: float = 1.20

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    def validate(self, *, require_sec: bool = True) -> None:
        if require_sec:
            if not self.sec_identity:
                raise ValueError("SEC_IDENTITY or SEC_USER_AGENT with a real contact email is required")
            if not re.search(r"[^\s@]+@[^\s@]+\.[^\s@]+", self.sec_identity):
                raise ValueError("SEC identity must contain a contact email address")
        if not 0 < self.sec_requests_per_second <= 10:
            raise ValueError("SEC requests/second must be in (0, 10]")
        if self.xbrl_mode not in {"none", "key_facts", "all"}:
            raise ValueError("xbrl_mode must be none, key_facts, or all")
        if self.max_document_bytes <= 0:
            raise ValueError("max_document_bytes must be positive")
        if not self.include_forms:
            raise ValueError("include_forms must not be empty")
        overlap = {x.upper() for x in self.include_forms} & {x.upper() for x in self.exclude_forms}
        if overlap:
            raise ValueError(f"forms cannot be both included and excluded: {sorted(overlap)}")

    def to_jsonable(self) -> dict:
        raw = asdict(self)
        raw["db_path"] = str(self.db_path)
        raw["data_dir"] = str(self.data_dir)
        raw["symbol_metadata_path"] = str(self.symbol_metadata_path)
        raw["include_forms"] = sorted(self.include_forms)
        raw["exclude_forms"] = sorted(self.exclude_forms)
        return raw

    @classmethod
    def from_env(cls, **overrides) -> PipelineConfig:
        workers = WorkerConfig(
            download=int(os.getenv("ESL_SEC_DOWNLOAD_WORKERS", "4")),
            yahoo=int(os.getenv("ESL_YAHOO_WORKERS", "2")),
            parse_core=int(os.getenv("ESL_PARSE_CORE_WORKERS", "4")),
            parse_event=int(os.getenv("ESL_PARSE_EVENT_WORKERS", "3")),
            parse_holdings=int(os.getenv("ESL_PARSE_HOLDINGS_WORKERS", "2")),
            parse_other=int(os.getenv("ESL_PARSE_OTHER_WORKERS", "3")),
            semantic_core=int(os.getenv("ESL_SEMANTIC_CORE_WORKERS", "4")),
            semantic_event=int(os.getenv("ESL_SEMANTIC_EVENT_WORKERS", "3")),
            semantic_holdings=int(os.getenv("ESL_SEMANTIC_HOLDINGS_WORKERS", "2")),
            semantic_other=int(os.getenv("ESL_SEMANTIC_OTHER_WORKERS", "3")),
            finalize=int(os.getenv("ESL_FINALIZE_WORKERS", "1")),
        )
        values = dict(
            db_path=Path(os.getenv("ESL_SEC_DB_PATH", "data/sec_yfinance_structured.db")),
            data_dir=Path(os.getenv("ESL_SEC_DATA_DIR", "data/sec_yfinance")),
            symbol_metadata_path=Path(os.getenv(
                "ESL_SYMBOL_METADATA_PATH",
                r"D:\DEV\AnotherNetworkFactory\RAW_DATA\metadata\symbol_metadata.parquet",
            )),
            sec_identity=os.getenv("SEC_IDENTITY") or os.getenv("SEC_USER_AGENT"),
            sec_requests_per_second=float(os.getenv("SEC_REQUESTS_PER_SECOND", "4")),
            sec_max_attempts=int(os.getenv("SEC_MAX_ATTEMPTS", "6")),
            yahoo_min_interval_seconds=float(os.getenv("YF_MIN_INTERVAL_SECONDS", "0.75")),
            workers=workers,
        )
        values.update(overrides)
        return cls(**values)

    @classmethod
    def from_json(cls, path: str | Path, **overrides) -> PipelineConfig:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if "workers" in raw:
            raw["workers"] = WorkerConfig(**raw["workers"])
        for key in ("db_path", "data_dir", "symbol_metadata_path"):
            if key in raw:
                raw[key] = Path(raw[key])
        for key in ("include_forms", "exclude_forms"):
            if key in raw:
                raw[key] = frozenset(str(x).upper() for x in raw[key])
        raw.update(overrides)
        raw.setdefault("sec_identity", os.getenv("SEC_IDENTITY") or os.getenv("SEC_USER_AGENT"))
        return cls(**raw)

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: Path = Path("data/equity_semantic.db")
    data_dir: Path = Path("data")
    sec_identity: str | None = None
    sec_requests_per_second: float = 5.0
    sec_max_attempts: int = 5
    sec_cache_ttl_hours: float = 6.0
    yf_min_interval_seconds: float = 1.0
    yf_max_attempts: int = 5
    yf_cache_ttl_hours: float = 24.0

    @classmethod
    def from_env(cls, *, require_sec_identity: bool = False) -> Settings:
        settings = cls(
            db_path=Path(os.getenv("ESL_DB_PATH", "data/equity_semantic.db")),
            data_dir=Path(os.getenv("ESL_DATA_DIR", "data")),
            sec_identity=os.getenv("SEC_IDENTITY") or os.getenv("SEC_USER_AGENT"),
            sec_requests_per_second=float(os.getenv("SEC_REQUESTS_PER_SECOND", "5")),
            sec_max_attempts=int(os.getenv("SEC_MAX_ATTEMPTS", "5")),
            sec_cache_ttl_hours=float(os.getenv("SEC_CACHE_TTL_HOURS", "6")),
            yf_min_interval_seconds=float(os.getenv("YF_MIN_INTERVAL_SECONDS", "1.0")),
            yf_max_attempts=int(os.getenv("YF_MAX_ATTEMPTS", "5")),
            yf_cache_ttl_hours=float(os.getenv("YF_CACHE_TTL_HOURS", "24")),
        )
        if require_sec_identity:
            settings.validate_sec_identity()
        return settings

    def validate_sec_identity(self) -> None:
        if not self.sec_identity:
            raise ValueError("SEC_IDENTITY is required, e.g. 'Your Name you@example.com'.")
        if not re.search(r"[^\s@]+@[^\s@]+\.[^\s@]+", self.sec_identity):
            raise ValueError("SEC_IDENTITY must contain a contact email address.")
        if self.sec_requests_per_second <= 0 or self.sec_requests_per_second > 10:
            raise ValueError("SEC_REQUESTS_PER_SECOND must be greater than 0 and no more than 10.")

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def stable_id(*parts: Any) -> str:
    raw = "\x1f".join("" if p is None else str(p) for p in parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]

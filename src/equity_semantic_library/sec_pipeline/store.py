from __future__ import annotations

from pathlib import Path
from typing import Any

from .store_base import StoreBase
from .store_core import CoreStoreMixin
from .store_dag import DagStoreMixin
from .store_utils import canonical_json, stable_id, utc_now
from .write_queue import WriteQueue


class PipelineStore(DagStoreMixin, CoreStoreMixin, StoreBase):
    def __init__(self, path: str | Path, *, write_queue: Any | None = None):
        super().__init__(path, write_queue=write_queue)


__all__ = ["PipelineStore", "WriteQueue", "canonical_json", "stable_id", "utc_now"]

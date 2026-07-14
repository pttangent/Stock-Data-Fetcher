from pathlib import Path

from equity_semantic_library.db import Database
from equity_semantic_library.validation import validate_database


def test_empty_initialized_database_passes_structural_checks(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite")
    db.initialize()
    report = validate_database(db)
    assert report["passed"] is True


def test_failed_latest_run_blocks_release(tmp_path: Path):
    db = Database(tmp_path / "failed.db")
    db.initialize()
    run_id = db.start_run({}, ["AAPL"])
    db.set_queue_status(run_id, "AAPL", "failed", error="network")
    db.finish_run(run_id)
    report = validate_database(db)
    assert report["passed"] is False
    latest = next(check for check in report["checks"] if check["name"] == "latest_run_released")
    assert latest["count"] == 1

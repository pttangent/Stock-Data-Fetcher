from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from typing import Any

from .store_utils import canonical_json, stable_id, utc_now


class DagStoreMixin:
    def schedule_task(self, *, run_id: str, task_type: str, lane: str, priority: int, symbol: str | None = None, cik: str | None = None, accession: str | None = None, form: str | None = None, payload: dict[str, Any] | None = None, max_attempts: int = 3, dependencies: list[str] | None = None) -> str:
        task_id = stable_id("task", run_id, task_type, symbol, accession)
        now = utc_now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """INSERT OR IGNORE INTO dag_task(task_id,run_id,task_type,lane,priority,symbol,cik,accession,form,payload_json,status,attempt_count,max_attempts,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,'pending',0,?,?,?)""",
                (task_id, run_id, task_type, lane, int(priority), symbol, cik, accession, form, canonical_json(payload or {}), int(max_attempts), now, now),
            )
            for dep in dependencies or []:
                conn.execute("INSERT OR IGNORE INTO dag_dependency(task_id,depends_on_task_id) VALUES(?,?)", (task_id, dep))
            conn.commit()
        return task_id

    def claim_task(self, *, run_id: str, lane: str, worker_id: str, lease_seconds: int) -> dict[str, Any] | None:
        now = utc_now()
        expiry = (datetime.now(UTC) + timedelta(seconds=lease_seconds)).isoformat().replace("+00:00", "Z")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE dag_task SET status='pending',lease_owner=NULL,lease_expires_at=NULL WHERE run_id=? AND status='running' AND lease_expires_at<?",
                (run_id, now),
            )
            row = conn.execute(
                """SELECT t.* FROM dag_task t
                WHERE t.run_id=? AND t.lane=? AND t.status='pending'
                  AND (t.not_before IS NULL OR t.not_before<=?)
                  AND NOT EXISTS(
                    SELECT 1 FROM dag_dependency d JOIN dag_task p ON p.task_id=d.depends_on_task_id
                    WHERE d.task_id=t.task_id AND p.status NOT IN ('completed','skipped')
                  )
                ORDER BY t.priority,t.created_at LIMIT 1""",
                (run_id, lane, now),
            ).fetchone()
            if row is None:
                conn.rollback()
                return None
            changed = conn.execute(
                """UPDATE dag_task SET status='running',attempt_count=attempt_count+1,lease_owner=?,lease_expires_at=?,updated_at=?
                WHERE task_id=? AND status='pending'""",
                (worker_id, expiry, now, row["task_id"]),
            ).rowcount
            if not changed:
                conn.rollback()
                return None
            conn.execute(
                "INSERT INTO dag_event(run_id,task_id,occurred_at,event_type,worker_id,payload_json) VALUES(?,?,?,'claimed',?,?)",
                (run_id, row["task_id"], now, worker_id, "{}"),
            )
            conn.commit()
            result = dict(row)
            result["payload"] = json.loads(result.pop("payload_json"))
            return result

    def complete_task(self, task_id: str, worker_id: str, payload: dict[str, Any] | None = None) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            run_id = conn.execute("SELECT run_id FROM dag_task WHERE task_id=?", (task_id,)).fetchone()[0]
            conn.execute("UPDATE dag_task SET status='completed',lease_owner=NULL,lease_expires_at=NULL,updated_at=?,completed_at=?,last_error=NULL WHERE task_id=?", (now, now, task_id))
            conn.execute("INSERT INTO dag_event(run_id,task_id,occurred_at,event_type,worker_id,payload_json) VALUES(?,?,?,'completed',?,?)", (run_id, task_id, now, worker_id, canonical_json(payload or {})))
            conn.commit()

    def fail_task(self, task: dict[str, Any], worker_id: str, error: Exception) -> None:
        now = utc_now()
        terminal = int(task.get("attempt_count", 0)) + 1 >= int(task.get("max_attempts", 1))
        status = "failed" if terminal else "pending"
        delay = min(300, 2 ** max(1, int(task.get("attempt_count", 0))))
        not_before = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat().replace("+00:00", "Z") if not terminal else None
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE dag_task SET status=?,not_before=?,lease_owner=NULL,lease_expires_at=NULL,last_error=?,updated_at=? WHERE task_id=?", (status, not_before, f"{type(error).__name__}: {error}", now, task["task_id"]))
            conn.execute("INSERT INTO dag_event(run_id,task_id,occurred_at,event_type,worker_id,payload_json) VALUES(?,?,?,'failed',?,?)", (task["run_id"], task["task_id"], now, worker_id, canonical_json({"error_type": type(error).__name__, "message": str(error), "terminal": terminal})))
            conn.execute("INSERT OR REPLACE INTO pipeline_issue(issue_id,run_id,task_id,symbol,accession,stage,severity,code,message,context_json,occurred_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (stable_id("issue", task["task_id"], task.get("attempt_count"), type(error).__name__, str(error)), task["run_id"], task["task_id"], task.get("symbol"), task.get("accession"), task["task_type"], "error" if terminal else "warning", type(error).__name__, str(error), canonical_json(task.get("payload", {})), now))
            conn.commit()

    def cancel_blocked_tasks(self, run_id: str) -> int:
        now = utc_now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """SELECT DISTINCT t.task_id FROM dag_task t
                JOIN dag_dependency d ON d.task_id=t.task_id
                JOIN dag_task p ON p.task_id=d.depends_on_task_id
                WHERE t.run_id=? AND t.status='pending' AND p.status IN ('failed','cancelled')""",
                (run_id,),
            ).fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE dag_task SET status='cancelled',last_error='blocked by failed dependency',updated_at=?,completed_at=? WHERE task_id=?",
                    (now, now, row[0]),
                )
                conn.execute(
                    "INSERT INTO dag_event(run_id,task_id,occurred_at,event_type,payload_json) VALUES(?,?,?,'cancelled',?)",
                    (run_id, row[0], now, canonical_json({"reason": "failed_dependency"})),
                )
            conn.commit()
            return len(rows)

    def pending_count(self, run_id: str) -> int:
        with self.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM dag_task WHERE run_id=? AND status IN ('pending','running')", (run_id,)).fetchone()[0]

    def task_counts(self, run_id: str) -> dict[str, int]:
        with self.connect() as conn:
            return {r["status"]: r["n"] for r in conn.execute("SELECT status,COUNT(*) n FROM dag_task WHERE run_id=? GROUP BY status", (run_id,))}

    def sections_for_filing(self, filing_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM filing_section WHERE filing_id=? ORDER BY ordinal", (filing_id,))]

    def documents_for_filing(self, filing_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM filing_document WHERE filing_id=? ORDER BY sequence", (filing_id,))]

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(sql, params)]

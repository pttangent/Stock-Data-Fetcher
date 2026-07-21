from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import Database
from .util import sha256_bytes


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    count: int
    detail: str


def validate_database(database: Database) -> dict[str, Any]:
    checks: list[Check] = []
    with database.connect() as conn:
        foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
        checks.append(Check("foreign_keys", not foreign_keys, len(foreign_keys), "No orphan rows"))

        placeholder_count = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM issuer
               WHERE lower(COALESCE(legal_name,'')) IN ('<na>','nan','none','null'))
              +
              (SELECT COUNT(*) FROM company_profile_snapshot
               WHERE lower(COALESCE(long_name,'')) IN ('<na>','nan','none','null')
                  OR lower(COALESCE(short_name,'')) IN ('<na>','nan','none','null'))
            """
        ).fetchone()[0]
        checks.append(
            Check(
                "no_placeholder_names",
                placeholder_count == 0,
                placeholder_count,
                "No sentinel null strings",
            )
        )

        duplicate_symbols = conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT symbol,COUNT(*) AS n FROM security
                WHERE status IN ('active','provisional','review_required')
                GROUP BY symbol HAVING n>1
            )
            """
        ).fetchone()[0]
        checks.append(
            Check(
                "unique_current_symbols",
                duplicate_symbols == 0,
                duplicate_symbols,
                "A current symbol maps to one security row",
            )
        )

        bad_documents = conn.execute(
            """
            SELECT COUNT(*) FROM source_document
            WHERE status IN ('downloaded','parsed')
              AND (content_hash IS NULL OR local_path IS NULL OR accession_number IS NULL)
            """
        ).fetchone()[0]
        checks.append(
            Check(
                "downloaded_documents_complete",
                bad_documents == 0,
                bad_documents,
                "Downloaded filings have provenance",
            )
        )

        bad_available = conn.execute(
            """
            SELECT COUNT(*) FROM source_document
            WHERE source='sec_edgar' AND available_at IS NULL
            """
        ).fetchone()[0]
        checks.append(
            Check(
                "sec_available_at",
                bad_available == 0,
                bad_available,
                "SEC documents have deterministic knowledge time",
            )
        )

        duplicate_sections = conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT document_id,section_key,content_hash,COUNT(*) AS n
                FROM filing_section GROUP BY document_id,section_key,content_hash HAVING n>1
            )
            """
        ).fetchone()[0]
        checks.append(
            Check(
                "no_duplicate_sections",
                duplicate_sections == 0,
                duplicate_sections,
                "Section writes are idempotent",
            )
        )

        bad_observation_order = conn.execute(
            """
            SELECT COUNT(*) FROM source_record
            WHERE last_observed_at < observed_at
            """
        ).fetchone()[0]
        checks.append(
            Check(
                "observation_time_order",
                bad_observation_order == 0,
                bad_observation_order,
                "Last observation is not before first observation",
            )
        )

        accepted_facts_without_evidence = conn.execute(
            """
            SELECT COUNT(*) FROM semantic_fact
            WHERE status='accepted'
              AND (document_id IS NULL OR section_id IS NULL
                   OR verbatim_evidence IS NULL OR available_at IS NULL)
            """
        ).fetchone()[0]
        checks.append(
            Check(
                "accepted_facts_have_evidence",
                accepted_facts_without_evidence == 0,
                accepted_facts_without_evidence,
                "Accepted semantic facts are evidence-backed",
            )
        )

        accepted_relations_without_evidence = conn.execute(
            """
            SELECT COUNT(*) FROM company_relation
            WHERE status='accepted'
              AND (document_id IS NULL OR section_id IS NULL
                   OR verbatim_evidence IS NULL OR available_at IS NULL)
            """
        ).fetchone()[0]
        checks.append(
            Check(
                "accepted_relations_have_evidence",
                accepted_relations_without_evidence == 0,
                accepted_relations_without_evidence,
                "Accepted company relations are evidence-backed",
            )
        )

        stale_runs = conn.execute(
            "SELECT COUNT(*) FROM ingestion_run WHERE status='running' AND completed_at IS NOT NULL"
        ).fetchone()[0]
        checks.append(
            Check("run_status_consistent", stale_runs == 0, stale_runs, "Run state is coherent")
        )

        latest_run = conn.execute(
            "SELECT run_id,status FROM ingestion_run ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        latest_unresolved = 0
        detail = "No ingestion run yet"
        if latest_run is not None:
            latest_unresolved = conn.execute(
                """
                SELECT COUNT(*) FROM work_queue
                WHERE run_id=? AND status!='completed'
                """,
                (latest_run["run_id"],),
            ).fetchone()[0]
            detail = f"Latest run status={latest_run['status']}"
        checks.append(
            Check(
                "latest_run_released",
                latest_unresolved == 0,
                latest_unresolved,
                detail,
            )
        )

        downloaded = conn.execute(
            """
            SELECT document_id,local_path,content_hash FROM source_document
            WHERE status IN ('downloaded','parsed')
            """
        ).fetchall()

    missing_or_changed = 0
    for row in downloaded:
        path = Path(row["local_path"] or "")
        if not path.is_file():
            missing_or_changed += 1
            continue
        if sha256_bytes(path.read_bytes()) != row["content_hash"]:
            missing_or_changed += 1
    checks.append(
        Check(
            "downloaded_file_hashes",
            missing_or_changed == 0,
            missing_or_changed,
            "Downloaded filing files exist and match stored hashes",
        )
    )

    return {
        "passed": all(check.passed for check in checks),
        "checks": [check.__dict__ for check in checks],
    }

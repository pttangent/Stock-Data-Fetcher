#!/usr/bin/env python3
"""Export selected symbols from a batch database into individual SQLite databases."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def export_symbols(src_path: str, dst_dir: str, symbols: list[str]) -> None:
    src_path = Path(src_path)
    dst_dir = Path(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(src_path) as sconn:
        sconn.row_factory = sqlite3.Row

        # Get schema objects (tables first, then indexes, then views)
        schema_rows = sconn.execute(
            """SELECT type, name, sql FROM sqlite_master
            WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'
            ORDER BY CASE type WHEN 'table' THEN 1 WHEN 'index' THEN 2 WHEN 'view' THEN 3 ELSE 4 END, name"""
        ).fetchall()

        for symbol in symbols:
            dst_path = dst_dir / f"{symbol.upper()}.db"
            print(f"Exporting {symbol}...", end=" ", flush=True)

            with sqlite3.connect(dst_path) as dconn:
                dconn.execute("PRAGMA journal_mode=WAL")

                # Create schema
                for typ, name, sql in schema_rows:
                    try:
                        dconn.execute(sql)
                    except Exception:
                        pass

                # 1. Copy symbol_universe row
                _copy_rows(sconn, dconn, "symbol_universe", "symbol=?", (symbol.upper(),))

                # 2. Copy issuer + security for this symbol
                sec_row = sconn.execute(
                    "SELECT security_id, issuer_id FROM security WHERE symbol=?",
                    (symbol.upper(),),
                ).fetchone()

                if sec_row:
                    _copy_rows(sconn, dconn, "issuer", "issuer_id=?", (sec_row["issuer_id"],))
                    _copy_rows(sconn, dconn, "security", "security_id=?", (sec_row["security_id"],))

                # 3. Copy filing-related tables
                _copy_rows(sconn, dconn, "filing", "symbol=?", (symbol.upper(),))
                _copy_rows(sconn, dconn, "filing_overflow", "symbol=?", (symbol.upper(),))
                _copy_rows(sconn, dconn, "yahoo_profile_snapshot", "security_id=?", (sec_row["security_id"],) if sec_row else ("",))

                # 4. Copy filing-linked tables
                filing_ids = [
                    r[0] for r in sconn.execute(
                        "SELECT filing_id FROM filing WHERE symbol=?", (symbol.upper(),)
                    ).fetchall()
                ]

                if filing_ids:
                    ph = ",".join("?" for _ in filing_ids)
                    for table in [
                        "filing_document", "filing_section", "filing_table",
                        "evidence_snippet", "semantic_candidate", "semantic_assertion",
                        "semantic_review", "candidate_promotion", "company_relation",
                        "section_semantic_context", "event_ledger", "form13f_holding", "xbrl_fact",
                    ]:
                        _copy_rows(sconn, dconn, table, f"filing_id IN ({ph})", tuple(filing_ids))

                # 5. Copy pipeline tables
                run_ids = [
                    r[0] for r in sconn.execute(
                        "SELECT DISTINCT run_id FROM dag_task WHERE symbol=?", (symbol.upper(),)
                    ).fetchall()
                ]

                if run_ids:
                    rph = ",".join("?" for _ in run_ids)
                    _copy_rows(sconn, dconn, "pipeline_run", f"run_id IN ({rph})", tuple(run_ids))
                    _copy_rows(sconn, dconn, "dag_task", f"run_id IN ({rph})", tuple(run_ids))

                    # dag_dependency - need task_ids
                    task_ids = [
                        r[0] for r in sconn.execute(
                            f"SELECT task_id FROM dag_task WHERE run_id IN ({rph})", tuple(run_ids)
                        ).fetchall()
                    ]
                    if task_ids:
                        tph = ",".join("?" for _ in task_ids)
                        _copy_rows(
                            sconn, dconn, "dag_dependency",
                            f"task_id IN ({tph}) OR depends_on_task_id IN ({tph})",
                            tuple(task_ids) + tuple(task_ids),
                        )

                    _copy_rows(sconn, dconn, "dag_event", f"run_id IN ({rph})", tuple(run_ids))
                    _copy_rows(sconn, dconn, "pipeline_issue", f"run_id IN ({rph})", tuple(run_ids))

                # 6. Copy schema_migration
                _copy_rows(sconn, dconn, "schema_migration", "1=1", ())

                dconn.commit()

            # Count total rows
            total = sconn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
            print(f"done")


def _copy_rows(
    sconn: sqlite3.Connection,
    dconn: sqlite3.Connection,
    table: str,
    where: str,
    params: tuple,
) -> int:
    """Copy rows matching WHERE from source to destination table."""
    try:
        cols = [r[1] for r in sconn.execute(f"PRAGMA table_info({table})").fetchall()]
    except Exception:
        return 0
    if not cols:
        return 0

    col_str = ",".join(cols)
    ph = ",".join("?" for _ in cols)

    try:
        rows = sconn.execute(f"SELECT {col_str} FROM {table} WHERE {where}", params).fetchall()
    except Exception:
        return 0

    if not rows:
        return 0

    try:
        dconn.executemany(f"INSERT OR IGNORE INTO {table}({col_str}) VALUES({ph})", rows)
    except Exception:
        return 0

    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", required=True)
    parser.add_argument("--dst-dir", required=True)
    parser.add_argument("--symbols", required=True)
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")]
    export_symbols(args.src, args.dst_dir, symbols)
    return 0


if __name__ == "__main__":
    sys.exit(main())

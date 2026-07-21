from __future__ import annotations

import uuid
from typing import Any

from .store_utils import canonical_json, utc_now


class CoreStoreMixin:
    def start_run(self, config: dict[str, Any], source_path: str | None, source_hash: str | None) -> str:
        run_id = f"sec-run:{uuid.uuid4().hex}"
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO pipeline_run(run_id,started_at,status,config_json,source_metadata_path,source_metadata_sha256) VALUES(?,?,'running',?,?,?)",
                (run_id, utc_now(), canonical_json(config), source_path, source_hash),
            )
            conn.commit()
        return run_id

    def finish_run(self, run_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            counts = {row["status"]: row["n"] for row in conn.execute(
                "SELECT status,COUNT(*) n FROM dag_task WHERE run_id=? GROUP BY status", (run_id,)
            )}
            failed = counts.get("failed", 0) + counts.get("cancelled", 0)
            pending = counts.get("pending", 0) + counts.get("running", 0)
            status = "failed" if failed and not counts.get("completed", 0) else ("partial" if failed or pending else "completed")
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE pipeline_run SET completed_at=?,status=?,task_count=?,completed_task_count=?,failed_task_count=? WHERE run_id=?",
                (utc_now(), status, sum(counts.values()), counts.get("completed", 0), failed, run_id),
            )
            conn.commit()
            return {"run_id": run_id, "status": status, "counts": counts}

    def upsert_universe_rows(self, rows: list[dict[str, Any]]) -> None:
        now = utc_now()
        sql = """
        INSERT INTO symbol_universe(symbol,source_symbol,company_name,sector_code,industry_code,market_cap,rank,exchange,country,quote_type,security_type,is_etf,source_path,source_row_hash,imported_at)
        VALUES(:symbol,:source_symbol,:company_name,:sector_code,:industry_code,:market_cap,:rank,:exchange,:country,:quote_type,:security_type,:is_etf,:source_path,:source_row_hash,:imported_at)
        ON CONFLICT(symbol) DO UPDATE SET
          source_symbol=excluded.source_symbol, company_name=excluded.company_name,
          sector_code=excluded.sector_code, industry_code=excluded.industry_code,
          market_cap=excluded.market_cap, rank=excluded.rank, exchange=excluded.exchange,
          country=excluded.country, quote_type=excluded.quote_type,
          security_type=excluded.security_type, is_etf=excluded.is_etf,
          source_path=excluded.source_path, source_row_hash=excluded.source_row_hash,
          imported_at=excluded.imported_at
        """
        payload = [{**row, "imported_at": now} for row in rows]
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.executemany(sql, payload)
            conn.commit()

    def universe(self, limit: int | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM symbol_universe WHERE COALESCE(is_etf,0)=0 ORDER BY market_cap DESC NULLS LAST, rank ASC NULLS LAST, symbol"
        if limit:
            sql += f" LIMIT {int(limit)}"
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(sql)]

    def upsert_identity(self, *, symbol: str, cik: str, legal_name: str | None, metadata: dict[str, Any]) -> tuple[str, str]:
        cik = str(cik).zfill(10)
        issuer_id = f"issuer:sec:{cik}"
        security_id = f"security:{symbol.upper()}"
        now = utc_now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """INSERT INTO issuer(issuer_id,cik,legal_name,sic,sic_description,state_of_incorporation,country,identity_status,first_seen_at,last_seen_at)
                VALUES(?,?,?,?,?,?,?,'sec_resolved',?,?)
                ON CONFLICT(issuer_id) DO UPDATE SET legal_name=COALESCE(excluded.legal_name,issuer.legal_name),sic=COALESCE(excluded.sic,issuer.sic),sic_description=COALESCE(excluded.sic_description,issuer.sic_description),state_of_incorporation=COALESCE(excluded.state_of_incorporation,issuer.state_of_incorporation),last_seen_at=excluded.last_seen_at""",
                (issuer_id, cik, legal_name, metadata.get("sic"), metadata.get("sicDescription"), metadata.get("stateOfIncorporation"), metadata.get("country"), now, now),
            )
            conn.execute(
                """INSERT INTO security(security_id,issuer_id,symbol,exchange,currency,status,first_seen_at,last_seen_at)
                VALUES(?,?,?,?,?,'active',?,?)
                ON CONFLICT(security_id) DO UPDATE SET issuer_id=excluded.issuer_id,exchange=COALESCE(excluded.exchange,security.exchange),last_seen_at=excluded.last_seen_at""",
                (security_id, issuer_id, symbol.upper(), (metadata.get("exchanges") or [None])[0], None, now, now),
            )
            conn.commit()
        return issuer_id, security_id

    def upsert_filing(self, row: dict[str, Any]) -> str:
        filing_id = row.get("filing_id") or f"filing:sec:{row['accession']}"
        data = {**row, "filing_id": filing_id, "metadata_json": canonical_json(row.get("metadata", {}))}
        sql = """
        INSERT INTO filing(filing_id,issuer_id,security_id,symbol,cik,accession,form,base_form,form_group,filing_date,report_date,accepted_at,available_at,available_at_precision,primary_document,source_url,raw_storage_uri,raw_sha256,raw_bytes,compressed_bytes,retrieved_at,status,metadata_json)
        VALUES(:filing_id,:issuer_id,:security_id,:symbol,:cik,:accession,:form,:base_form,:form_group,:filing_date,:report_date,:accepted_at,:available_at,:available_at_precision,:primary_document,:source_url,:raw_storage_uri,:raw_sha256,:raw_bytes,:compressed_bytes,:retrieved_at,:status,:metadata_json)
        ON CONFLICT(accession) DO UPDATE SET
          raw_storage_uri=COALESCE(excluded.raw_storage_uri,filing.raw_storage_uri),
          raw_sha256=COALESCE(excluded.raw_sha256,filing.raw_sha256),
          raw_bytes=COALESCE(excluded.raw_bytes,filing.raw_bytes),
          compressed_bytes=COALESCE(excluded.compressed_bytes,filing.compressed_bytes),
          retrieved_at=COALESCE(excluded.retrieved_at,filing.retrieved_at),
          status=excluded.status, metadata_json=excluded.metadata_json
        """
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(sql, data)
            conn.commit()
        return filing_id

    def filing_by_accession(self, accession: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM filing WHERE accession=?", (accession,)).fetchone()
            return dict(row) if row else None

    def clear_semantic_filing(self, filing_id: str) -> None:
        """Clear derived semantics while preserving parsed SEC structure and review history."""
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "DELETE FROM candidate_promotion WHERE candidate_id IN (SELECT candidate_id FROM semantic_candidate WHERE filing_id=?)",
                (filing_id,),
            )
            conn.execute("DELETE FROM company_relation WHERE filing_id=?", (filing_id,))
            conn.execute("DELETE FROM semantic_assertion WHERE filing_id=?", (filing_id,))
            conn.execute("DELETE FROM semantic_candidate WHERE filing_id=?", (filing_id,))
            conn.execute("DELETE FROM section_semantic_context WHERE filing_id=?", (filing_id,))
            conn.execute("DELETE FROM event_ledger WHERE filing_id=?", (filing_id,))
            conn.execute("DELETE FROM evidence_snippet WHERE filing_id=?", (filing_id,))
            conn.commit()

    def clear_parsed_filing(self, filing_id: str) -> None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "DELETE FROM candidate_promotion WHERE candidate_id IN (SELECT candidate_id FROM semantic_candidate WHERE filing_id=?)",
                (filing_id,),
            )
            conn.execute("DELETE FROM company_relation WHERE filing_id=?", (filing_id,))
            conn.execute("DELETE FROM semantic_assertion WHERE filing_id=?", (filing_id,))
            conn.execute("DELETE FROM semantic_candidate WHERE filing_id=?", (filing_id,))
            conn.execute("DELETE FROM section_semantic_context WHERE filing_id=?", (filing_id,))
            conn.execute("DELETE FROM event_ledger WHERE filing_id=?", (filing_id,))
            conn.execute("DELETE FROM evidence_snippet WHERE filing_id=?", (filing_id,))
            conn.execute("DELETE FROM form13f_holding WHERE filing_id=?", (filing_id,))
            conn.execute("DELETE FROM filing_document WHERE filing_id=?", (filing_id,))
            conn.commit()

    def insert_many(self, table: str, rows: list[dict[str, Any]], *, replace: bool = False) -> None:
        if not rows:
            return
        columns = list(rows[0])
        placeholders = ",".join("?" for _ in columns)
        verb = "INSERT OR REPLACE" if replace else "INSERT OR IGNORE"
        sql = f"{verb} INTO {table}({','.join(columns)}) VALUES({placeholders})"
        values = [tuple(canonical_json(row[c]) if isinstance(row[c], (dict, list)) else row[c] for c in columns) for row in rows]
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.executemany(sql, values)
            conn.commit()

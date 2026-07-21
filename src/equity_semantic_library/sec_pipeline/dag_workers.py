from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import time
from typing import Any

from .archive import (
    extract_inline_xbrl, extract_sections, extract_tables, html_to_text, parse_13f,
    parse_documents, parse_xml, read_storage_uri, sha256_bytes,
)
from .forms import LANE_BY_TASK, PARSE_TASK_BY_GROUP, SEMANTIC_TASK_BY_GROUP, base_form, form_group, form_priority
from .semantic import (
    extract_13f_relations, extract_8k_events, extract_offering_semantics,
    extract_proxy_semantics, extract_regulatory_semantics, extract_topics_and_concepts,
)
from .store import canonical_json, stable_id, utc_now

PARSER_VERSION = "sec-dag-parser-v2"


class DagWorkerMixin:
    def _discover_company(self, task: dict[str, Any]) -> dict[str, Any]:
        archive = self._ensure_sec()
        symbol = task["symbol"]
        match = archive.lookup(symbol)
        if not match:
            raise LookupError(f"No SEC CIK mapping for {symbol}")
        root, filings = archive.discover_filings(
            match["cik"], self.policy, refresh=bool(task["payload"].get("refresh")),
            from_date=self.config.from_date, to_date=self.config.to_date,
        )
        issuer_id, security_id = self.store.upsert_identity(
            symbol=symbol, cik=match["cik"], legal_name=root.get("name") or match.get("title"), metadata=root
        )
        for filing in filings:
            form = str(filing.get("form") or "").upper()
            group = form_group(form)
            if not group:
                continue
            accession = str(filing["accessionNumber"])
            self.store.schedule_task(
                run_id=task["run_id"], task_type="download_filing", lane="download",
                priority=int(task["priority"]) + form_priority(form), symbol=symbol, cik=match["cik"],
                accession=accession, form=form,
                payload={"issuer_id": issuer_id, "security_id": security_id, "filing": filing, "form_group": group},
                max_attempts=self.config.task_max_attempts,
            )
        return {"cik": match["cik"], "selected_filings": len(filings)}

    def _disk_ok(self) -> None:
        target = self.config.data_dir
        target.mkdir(parents=True, exist_ok=True)
        free_gb = shutil.disk_usage(target).free / 1024**3
        if free_gb <= self.config.stop_free_gb:
            raise RuntimeError(f"free space {free_gb:.2f} GiB <= stop threshold {self.config.stop_free_gb:.2f} GiB")

    def _download_filing(self, task: dict[str, Any]) -> dict[str, Any]:
        self._disk_ok()
        archive = self._ensure_sec()
        metadata = task["payload"]["filing"]
        evidence = archive.download_complete(task["symbol"], task["cik"], metadata)
        form = task["form"]
        group = task["payload"]["form_group"]
        available_at = metadata.get("acceptanceDateTime") or metadata.get("filingDate") or evidence["fetched_at"]
        precision = "datetime" if metadata.get("acceptanceDateTime") else "date"
        filing_id = self.store.upsert_filing({
            "issuer_id": task["payload"]["issuer_id"], "security_id": task["payload"]["security_id"],
            "symbol": task["symbol"], "cik": task["cik"], "accession": task["accession"], "form": form,
            "base_form": base_form(form), "form_group": group, "filing_date": metadata.get("filingDate"),
            "report_date": metadata.get("reportDate"), "accepted_at": metadata.get("acceptanceDateTime"),
            "available_at": available_at, "available_at_precision": precision,
            "primary_document": metadata.get("primaryDocument"), "source_url": evidence["url"],
            "raw_storage_uri": evidence["storage_uri"], "raw_sha256": evidence["sha256"],
            "raw_bytes": evidence["bytes"], "compressed_bytes": evidence["compressed_bytes"],
            "retrieved_at": evidence["fetched_at"], "status": "downloaded", "metadata": metadata,
        })
        parse_task = PARSE_TASK_BY_GROUP[group]
        self.store.schedule_task(
            run_id=task["run_id"], task_type=parse_task, lane=LANE_BY_TASK[parse_task],
            priority=int(task["priority"]) + 100, symbol=task["symbol"], cik=task["cik"],
            accession=task["accession"], form=form,
            payload={"filing_id": filing_id, "expected_sha256": evidence["sha256"]},
            max_attempts=self.config.task_max_attempts, dependencies=[task["task_id"]],
        )
        return {"filing_id": filing_id, "bytes": evidence["bytes"], "compressed_bytes": evidence["compressed_bytes"]}

    def _parse_filing(self, task: dict[str, Any]) -> dict[str, Any]:
        filing = self.store.filing_by_accession(task["accession"])
        if not filing:
            raise LookupError(task["accession"])
        raw = read_storage_uri(filing["raw_storage_uri"])
        actual_sha = sha256_bytes(raw)
        expected = task["payload"].get("expected_sha256") or filing.get("raw_sha256")
        if expected and actual_sha.lower() != str(expected).lower():
            raise ValueError(f"SHA256 mismatch expected={expected} actual={actual_sha}")
        self.store.clear_parsed_filing(filing["filing_id"])
        documents = parse_documents(raw)
        if not documents:
            raise ValueError("complete submission contains no <DOCUMENT> blocks")
        primary_name = Path(str(filing.get("primary_document") or "").replace("\\", "/")).name.lower()
        document_rows: list[dict[str, Any]] = []
        section_rows: list[dict[str, Any]] = []
        table_rows: list[dict[str, Any]] = []
        fact_rows: list[dict[str, Any]] = []
        holding_rows: list[dict[str, Any]] = []
        group = filing["form_group"]
        for index, doc in enumerate(documents, 1):
            payload: bytes = doc["payload"]
            payload_sha = sha256_bytes(payload)
            filename = Path(str(doc.get("filename") or "").replace("\\", "/")).name
            is_primary = bool(primary_name and filename.lower() == primary_name) or (not primary_name and index == 1)
            document_id = stable_id("document", filing["filing_id"], doc["sequence"], doc["document_type"], filename, payload_sha)
            document_rows.append({
                "document_id": document_id, "filing_id": filing["filing_id"], "sequence": doc["sequence"],
                "document_type": doc["document_type"], "filename": filename, "description": doc["description"],
                "content_kind": doc["content_kind"], "mime_type": doc["mime_type"], "is_primary": int(is_primary),
                "is_attachment": int(not is_primary), "source_start_byte": doc["source_start_byte"],
                "source_end_byte": doc["source_end_byte"], "raw_sha256": doc["block_sha256"],
                "payload_sha256": payload_sha, "payload_bytes": len(payload), "storage_uri": None,
            })
            if is_primary and doc["content_kind"] in {"html", "inline_xbrl", "text"}:
                text = html_to_text(payload) if doc["content_kind"] != "text" else payload.decode("utf-8", "replace")
                for ordinal, section in enumerate(extract_sections(text, filing["form"], group), 1):
                    section_id = stable_id("section", document_id, section["section_key"], sha256_bytes(section["text"].encode()))
                    section_rows.append({
                        "section_id": section_id, "filing_id": filing["filing_id"], "document_id": document_id,
                        "section_key": section["section_key"], "part": section["part"], "item": section["item"],
                        "title": section["title"], "ordinal": ordinal, "char_start": section["char_start"],
                        "char_end": section["char_end"], "text": section["text"],
                        "content_hash": sha256_bytes(section["text"].encode()), "extractor_version": PARSER_VERSION,
                    })
                if doc["content_kind"] in {"html", "inline_xbrl"}:
                    for table_index, table in enumerate(extract_tables(payload), 1):
                        rows_json = canonical_json(table["rows"])
                        table_rows.append({
                            "table_id": stable_id("table", document_id, table_index, sha256_bytes(rows_json.encode())),
                            "filing_id": filing["filing_id"], "document_id": document_id, "section_hint": None,
                            "caption": table["caption"], "row_count": table["row_count"],
                            "column_count": table["column_count"], "rows_json": rows_json,
                            "rows_hash": sha256_bytes(rows_json.encode()), "truncated": int(table["truncated"]),
                        })
            if doc["content_kind"] == "inline_xbrl":
                for fact_index, fact in enumerate(extract_inline_xbrl(payload, self.config.xbrl_mode), 1):
                    fact_rows.append({
                        "fact_id": stable_id("fact", document_id, fact_index, fact["concept"], fact["context_ref"], fact["value"]),
                        "filing_id": filing["filing_id"], "document_id": document_id, **fact,
                        "fact_available_at": filing["available_at"],
                    })
            if group == "holdings" and doc["content_kind"] in {"xml", "xbrl_xml"}:
                root = parse_xml(payload)
                if root is not None:
                    for holding in parse_13f(root):
                        holding_rows.append({
                            "holding_id": stable_id("holding", filing["filing_id"], holding["row_index"], holding["cusip"], holding["issuer_name"]),
                            "filing_id": filing["filing_id"], **{k: v for k, v in holding.items() if k != "row_index"},
                        })
        self.store.insert_many("filing_document", document_rows)
        self.store.insert_many("filing_section", section_rows)
        self.store.insert_many("filing_table", table_rows)
        self.store.insert_many("xbrl_fact", fact_rows)
        self.store.insert_many("form13f_holding", holding_rows)
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE filing SET raw_sha256=?,raw_bytes=?,status='parsed' WHERE filing_id=?", (actual_sha, len(raw), filing["filing_id"]))
            conn.commit()
        semantic_task = SEMANTIC_TASK_BY_GROUP[group]
        self.store.schedule_task(
            run_id=task["run_id"], task_type=semantic_task, lane=LANE_BY_TASK[semantic_task],
            priority=int(task["priority"]) + 100, symbol=task["symbol"], cik=task["cik"],
            accession=task["accession"], form=task["form"], payload={"filing_id": filing["filing_id"]},
            max_attempts=self.config.task_max_attempts, dependencies=[task["task_id"]],
        )
        return {"documents": len(document_rows), "sections": len(section_rows), "tables": len(table_rows), "xbrl_facts": len(fact_rows), "holdings": len(holding_rows)}

    def _semantic_filing(self, task: dict[str, Any]) -> dict[str, Any]:
        filing = self.store.filing_by_accession(task["accession"])
        if not filing:
            raise LookupError(task["accession"])
        sections = self.store.sections_for_filing(filing["filing_id"])
        counts = extract_topics_and_concepts(self.store, filing, sections, self.config.evidence_max_chars)
        group = filing["form_group"]
        if group == "event":
            counts["events"] = extract_8k_events(self.store, filing, sections, self.config.evidence_max_chars)
        elif group == "holdings":
            counts["holding_relations"] = extract_13f_relations(self.store, filing)
        elif group == "proxy":
            counts["proxy_assertions"] = extract_proxy_semantics(self.store, filing, sections, self.config.evidence_max_chars)
        elif group == "regulatory":
            counts["regulatory_assertions"] = extract_regulatory_semantics(self.store, filing, sections, self.config.evidence_max_chars)
        elif group == "offering":
            counts["offering_assertions"] = extract_offering_semantics(self.store, filing, sections, self.config.evidence_max_chars)
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE filing SET status='structured' WHERE filing_id=?", (filing["filing_id"],))
            conn.commit()
        return counts

    def _fetch_yahoo(self, task: dict[str, Any]) -> dict[str, Any]:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("yfinance is not installed") from exc
        self.yahoo_gate.wait()
        symbol = task["symbol"].replace(".", "-")
        last: Exception | None = None
        for attempt in range(1, self.config.yahoo_max_attempts + 1):
            try:
                payload = dict(yf.Ticker(symbol).info or {})
                if not payload:
                    raise ValueError("empty yfinance profile")
                rows = self.store.query("SELECT security_id FROM security WHERE symbol=?", (task["symbol"],))
                if not rows:
                    raise RuntimeError("SEC identity not available yet; retrying Yahoo task")
                security_id = rows[0]["security_id"]
                observed = utc_now()
                raw_json = canonical_json(payload)
                row = {
                    "snapshot_id": stable_id("yahoo", security_id, hashlib.sha256(raw_json.encode()).hexdigest()),
                    "security_id": security_id, "observed_at": observed, "available_at": observed,
                    "payload_hash": hashlib.sha256(raw_json.encode()).hexdigest(),
                    "market_cap": _int(payload.get("marketCap")), "enterprise_value": _int(payload.get("enterpriseValue")),
                    "sector_source": payload.get("sector"), "industry_source": payload.get("industry"),
                    "business_summary": payload.get("longBusinessSummary"), "raw_json": raw_json,
                }
                self.store.insert_many("yahoo_profile_snapshot", [row])
                return {"snapshot_id": row["snapshot_id"]}
            except Exception as exc:
                last = exc
                if attempt < self.config.yahoo_max_attempts:
                    time.sleep(min(20, 2 ** attempt))
        raise RuntimeError(f"Yahoo failed for {symbol}: {last}") from last

    def _finalize_symbol(self, task: dict[str, Any]) -> dict[str, Any]:
        counts = self.store.query("SELECT status,COUNT(*) n FROM filing WHERE symbol=? GROUP BY status", (task["symbol"],))
        return {"filings": {row["status"]: row["n"] for row in counts}}


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None

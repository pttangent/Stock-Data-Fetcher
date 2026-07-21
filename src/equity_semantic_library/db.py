from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .models import FilingMetadata, FilingSection, YahooProfile
from .util import canonical_json, normalize_missing, sha256_text, stable_id, utc_now

SCHEMA_VERSION = 1

_SCHEMA = r"""
CREATE TABLE IF NOT EXISTS schema_migration (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingestion_run (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('running','completed','partial','failed')),
    config_json TEXT NOT NULL,
    symbol_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS issuer (
    issuer_id TEXT PRIMARY KEY,
    cik TEXT UNIQUE,
    legal_name TEXT,
    sic TEXT,
    sic_description TEXT,
    state_of_incorporation TEXT,
    country TEXT,
    identity_status TEXT NOT NULL
        CHECK(identity_status IN ('sec_resolved','provisional','review_required')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS security (
    security_id TEXT PRIMARY KEY,
    issuer_id TEXT NOT NULL REFERENCES issuer(issuer_id),
    symbol TEXT NOT NULL,
    yahoo_symbol TEXT NOT NULL,
    exchange TEXT,
    quote_type TEXT,
    security_type TEXT,
    share_class TEXT,
    currency TEXT,
    is_etf INTEGER CHECK(is_etf IN (0,1) OR is_etf IS NULL),
    status TEXT NOT NULL CHECK(status IN ('active','provisional','review_required','inactive')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE(issuer_id, symbol)
);
CREATE INDEX IF NOT EXISTS idx_security_symbol ON security(symbol);

CREATE TABLE IF NOT EXISTS source_record (
    record_id TEXT PRIMARY KEY,
    security_id TEXT NOT NULL REFERENCES security(security_id),
    source TEXT NOT NULL,
    source_key TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    available_at TEXT,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ok','partial','error')),
    error_message TEXT,
    UNIQUE(source, source_key, payload_hash)
);
CREATE INDEX IF NOT EXISTS idx_source_record_security ON source_record(security_id, source);

CREATE TABLE IF NOT EXISTS company_profile_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    security_id TEXT NOT NULL REFERENCES security(security_id),
    source_record_id TEXT NOT NULL REFERENCES source_record(record_id),
    short_name TEXT,
    long_name TEXT,
    sector_source TEXT,
    industry_source TEXT,
    country TEXT,
    website TEXT,
    business_summary TEXT,
    market_cap INTEGER,
    enterprise_value INTEGER,
    shares_outstanding INTEGER,
    employees INTEGER,
    currency TEXT,
    exchange TEXT,
    quote_type TEXT,
    observed_at TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    UNIQUE(security_id, source_record_id)
);

CREATE TABLE IF NOT EXISTS source_document (
    document_id TEXT PRIMARY KEY,
    issuer_id TEXT NOT NULL REFERENCES issuer(issuer_id),
    source TEXT NOT NULL,
    source_key TEXT NOT NULL UNIQUE,
    form TEXT,
    filing_date TEXT,
    accepted_at TEXT,
    available_at TEXT,
    available_at_precision TEXT CHECK(available_at_precision IN ('datetime','date','unknown')),
    report_period TEXT,
    accession_number TEXT,
    primary_document TEXT,
    source_url TEXT NOT NULL,
    local_path TEXT,
    content_hash TEXT,
    media_type TEXT,
    retrieved_at TEXT,
    retrieval_method TEXT,
    status TEXT NOT NULL CHECK(status IN ('metadata_only','downloaded','parsed','error')),
    raw_metadata_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_source_document_issuer ON source_document(issuer_id, filing_date);

CREATE TABLE IF NOT EXISTS filing_section (
    section_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES source_document(document_id) ON DELETE CASCADE,
    section_key TEXT NOT NULL,
    title TEXT NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    text TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    UNIQUE(document_id, section_key, content_hash)
);

CREATE TABLE IF NOT EXISTS semantic_fact (
    fact_id TEXT PRIMARY KEY,
    security_id TEXT NOT NULL REFERENCES security(security_id),
    fact_type TEXT NOT NULL,
    value_json TEXT NOT NULL,
    document_id TEXT REFERENCES source_document(document_id),
    section_id TEXT REFERENCES filing_section(section_id),
    verbatim_evidence TEXT,
    char_start INTEGER,
    char_end INTEGER,
    available_at TEXT,
    effective_from TEXT,
    effective_to TEXT,
    confidence REAL,
    explicitness TEXT NOT NULL CHECK(explicitness IN ('explicit','inferred')),
    status TEXT NOT NULL CHECK(status IN ('staging','accepted','review_required','rejected')),
    extractor_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS company_relation (
    relation_id TEXT PRIMARY KEY,
    source_issuer_id TEXT NOT NULL REFERENCES issuer(issuer_id),
    target_entity_key TEXT NOT NULL,
    target_issuer_id TEXT REFERENCES issuer(issuer_id),
    relation_type TEXT NOT NULL,
    product_scope TEXT,
    document_id TEXT REFERENCES source_document(document_id),
    section_id TEXT REFERENCES filing_section(section_id),
    verbatim_evidence TEXT,
    available_at TEXT,
    effective_from TEXT,
    effective_to TEXT,
    confidence REAL,
    explicitness TEXT NOT NULL CHECK(explicitness IN ('explicit','inferred')),
    status TEXT NOT NULL CHECK(status IN ('staging','accepted','review_required','rejected')),
    extractor_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work_queue (
    run_id TEXT NOT NULL REFERENCES ingestion_run(run_id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK(status IN ('pending','running','completed','partial','failed','review_required')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(run_id, symbol)
);

CREATE TABLE IF NOT EXISTS ingestion_error (
    error_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES ingestion_run(run_id),
    symbol TEXT,
    stage TEXT NOT NULL,
    source TEXT NOT NULL,
    error_type TEXT NOT NULL,
    message TEXT NOT NULL,
    retryable INTEGER NOT NULL CHECK(retryable IN (0,1)),
    attempt INTEGER NOT NULL,
    occurred_at TEXT NOT NULL,
    context_json TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT OR IGNORE INTO schema_migration(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, utc_now()),
            )

    def start_run(self, config: dict[str, Any], symbols: list[str]) -> str:
        run_id = f"run:{uuid.uuid4().hex}"
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO ingestion_run(run_id, started_at, status, config_json, symbol_count) "
                "VALUES (?, ?, 'running', ?, ?)",
                (run_id, now, canonical_json(config), len(symbols)),
            )
            conn.executemany(
                (
                    "INSERT INTO work_queue(run_id, symbol, status, updated_at) "
                    "VALUES (?, ?, 'pending', ?)"
                ),
                [(run_id, symbol, now) for symbol in symbols],
            )
        return run_id

    def finish_run(self, run_id: str) -> None:
        with self.connect() as conn:
            counts = dict(
                conn.execute(
                    "SELECT status, COUNT(*) AS n FROM work_queue WHERE run_id=? GROUP BY status",
                    (run_id,),
                ).fetchall()
            )
            success = counts.get("completed", 0)
            errors = counts.get("failed", 0)
            partial = counts.get("partial", 0) + counts.get("review_required", 0)
            status = (
                "completed"
                if not errors and not partial
                else ("failed" if not success else "partial")
            )
            conn.execute(
                "UPDATE ingestion_run SET completed_at=?, status=?, success_count=?, error_count=? "
                "WHERE run_id=?",
                (utc_now(), status, success, errors + partial, run_id),
            )

    def set_queue_status(
        self,
        run_id: str,
        symbol: str,
        status: str,
        *,
        error: str | None = None,
        increment_attempt: bool = False,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE work_queue SET status=?, attempt_count=attempt_count+?, last_error=?, "
                "updated_at=? WHERE run_id=? AND symbol=?",
                (status, int(increment_attempt), error, utc_now(), run_id, symbol),
            )

    def upsert_issuer(
        self,
        *,
        cik: str | None,
        legal_name: str | None,
        identity_status: str,
        sic: str | None = None,
        sic_description: str | None = None,
        state_of_incorporation: str | None = None,
        country: str | None = None,
        provisional_key: str | None = None,
    ) -> str:
        cik = normalize_missing(cik)
        if cik:
            cik = str(cik).zfill(10)
            issuer_id = f"issuer:sec:{cik}"
        else:
            if not provisional_key:
                raise ValueError("provisional_key is required without CIK")
            issuer_id = stable_id("issuer:provisional", provisional_key)
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO issuer(
                    issuer_id,cik,legal_name,sic,sic_description,state_of_incorporation,country,
                    identity_status,first_seen_at,last_seen_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(issuer_id) DO UPDATE SET
                    cik=COALESCE(excluded.cik,issuer.cik),
                    legal_name=COALESCE(excluded.legal_name,issuer.legal_name),
                    sic=COALESCE(excluded.sic,issuer.sic),
                    sic_description=COALESCE(excluded.sic_description,issuer.sic_description),
                    state_of_incorporation=COALESCE(
                        excluded.state_of_incorporation,issuer.state_of_incorporation
                    ),
                    country=COALESCE(excluded.country,issuer.country),
                    identity_status=CASE
                        WHEN excluded.identity_status='sec_resolved' THEN 'sec_resolved'
                        ELSE issuer.identity_status END,
                    last_seen_at=excluded.last_seen_at
                """,
                (
                    issuer_id,
                    cik,
                    normalize_missing(legal_name),
                    normalize_missing(sic),
                    normalize_missing(sic_description),
                    normalize_missing(state_of_incorporation),
                    normalize_missing(country),
                    identity_status,
                    now,
                    now,
                ),
            )
        return issuer_id

    def upsert_security(
        self,
        *,
        issuer_id: str,
        symbol: str,
        yahoo_symbol: str,
        exchange: str | None = None,
        quote_type: str | None = None,
        security_type: str | None = None,
        currency: str | None = None,
        is_etf: bool | None = None,
        status: str = "active",
    ) -> str:
        security_id = stable_id("security", symbol)
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO security(
                    security_id,issuer_id,symbol,yahoo_symbol,exchange,quote_type,security_type,
                    currency,is_etf,status,first_seen_at,last_seen_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(security_id) DO UPDATE SET
                    issuer_id=CASE
                        WHEN (SELECT identity_status FROM issuer
                              WHERE issuer_id=excluded.issuer_id)='sec_resolved'
                            THEN excluded.issuer_id
                        ELSE security.issuer_id
                    END,
                    yahoo_symbol=excluded.yahoo_symbol,
                    exchange=COALESCE(excluded.exchange,security.exchange),
                    quote_type=COALESCE(excluded.quote_type,security.quote_type),
                    security_type=COALESCE(excluded.security_type,security.security_type),
                    currency=COALESCE(excluded.currency,security.currency),
                    is_etf=COALESCE(excluded.is_etf,security.is_etf),
                    status=CASE
                        WHEN security.status='active' THEN security.status
                        ELSE excluded.status
                    END,
                    last_seen_at=excluded.last_seen_at
                """,
                (
                    security_id,
                    issuer_id,
                    symbol,
                    yahoo_symbol,
                    normalize_missing(exchange),
                    normalize_missing(quote_type),
                    normalize_missing(security_type),
                    normalize_missing(currency),
                    None if is_etf is None else int(is_etf),
                    status,
                    now,
                    now,
                ),
            )
            conn.execute(
                "DELETE FROM issuer WHERE identity_status='provisional' "
                "AND NOT EXISTS (SELECT 1 FROM security WHERE security.issuer_id=issuer.issuer_id)"
            )
        return security_id

    def insert_source_record(
        self,
        *,
        security_id: str,
        source: str,
        source_key: str,
        observed_at: str,
        payload: dict[str, Any],
        available_at: str | None = None,
        status: str = "ok",
        error_message: str | None = None,
    ) -> str:
        payload_json = canonical_json(payload)
        payload_hash = sha256_text(payload_json)
        record_id = stable_id("record", source, source_key, payload_hash)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO source_record(
                    record_id,security_id,source,source_key,observed_at,last_observed_at,
                    available_at,payload_json,payload_hash,status,error_message
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(source,source_key,payload_hash) DO UPDATE SET
                    security_id=excluded.security_id,
                    last_observed_at=excluded.last_observed_at,
                    available_at=COALESCE(source_record.available_at,excluded.available_at),
                    status=excluded.status,
                    error_message=excluded.error_message
                """,
                (
                    record_id,
                    security_id,
                    source,
                    source_key,
                    observed_at,
                    observed_at,
                    available_at,
                    payload_json,
                    payload_hash,
                    status,
                    error_message,
                ),
            )
        return record_id

    def insert_yahoo_profile(self, security_id: str, record_id: str, profile: YahooProfile) -> str:
        data = profile.payload
        snapshot_id = stable_id("profile", security_id, record_id)

        def integer(key: str) -> int | None:
            value = normalize_missing(data.get(key))
            if value is None:
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO company_profile_snapshot(
                    snapshot_id,security_id,source_record_id,short_name,long_name,sector_source,
                    industry_source,country,website,business_summary,market_cap,enterprise_value,
                    shares_outstanding,employees,currency,exchange,quote_type,observed_at,raw_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    snapshot_id,
                    security_id,
                    record_id,
                    normalize_missing(data.get("shortName")),
                    normalize_missing(data.get("longName")),
                    normalize_missing(data.get("sector")),
                    normalize_missing(data.get("industry")),
                    normalize_missing(data.get("country")),
                    normalize_missing(data.get("website")),
                    normalize_missing(data.get("longBusinessSummary")),
                    integer("marketCap"),
                    integer("enterpriseValue"),
                    integer("sharesOutstanding"),
                    integer("fullTimeEmployees"),
                    normalize_missing(data.get("currency")),
                    normalize_missing(data.get("exchange")),
                    normalize_missing(data.get("quoteType")),
                    profile.observed_at,
                    canonical_json(data),
                ),
            )
            # Supplemental values may fill blanks but never replace SEC identity.
            conn.execute(
                """
                UPDATE security SET
                    exchange=COALESCE(exchange, ?),
                    quote_type=COALESCE(quote_type, ?),
                    security_type=COALESCE(security_type, ?),
                    currency=COALESCE(currency, ?),
                    is_etf=COALESCE(is_etf, ?),
                    last_seen_at=?
                WHERE security_id=?
                """,
                (
                    normalize_missing(data.get("exchange")),
                    normalize_missing(data.get("quoteType")),
                    normalize_missing(data.get("quoteType")),
                    normalize_missing(data.get("currency")),
                    1 if str(data.get("quoteType", "")).upper() == "ETF" else None,
                    utc_now(),
                    security_id,
                ),
            )
            conn.execute(
                """
                UPDATE issuer SET
                    legal_name=COALESCE(legal_name, ?),
                    country=COALESCE(country, ?),
                    last_seen_at=?
                WHERE issuer_id=(SELECT issuer_id FROM security WHERE security_id=?)
                """,
                (
                    normalize_missing(data.get("longName")),
                    normalize_missing(data.get("country")),
                    utc_now(),
                    security_id,
                ),
            )
        return snapshot_id

    def upsert_source_document(
        self,
        *,
        issuer_id: str,
        metadata: FilingMetadata,
        local_path: str | None = None,
        content_hash: str | None = None,
        media_type: str | None = None,
        retrieval_method: str | None = None,
        status: str = "metadata_only",
    ) -> str:
        document_id = f"document:sec:{metadata.accession_number}"
        available_at = metadata.accepted_at or metadata.filing_date
        precision = "datetime" if metadata.accepted_at else "date"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO source_document(
                    document_id,issuer_id,source,source_key,form,filing_date,accepted_at,available_at,
                    available_at_precision,report_period,accession_number,primary_document,source_url,
                    local_path,content_hash,media_type,retrieved_at,retrieval_method,status,raw_metadata_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(document_id) DO UPDATE SET
                    local_path=COALESCE(excluded.local_path,source_document.local_path),
                    content_hash=COALESCE(excluded.content_hash,source_document.content_hash),
                    media_type=COALESCE(excluded.media_type,source_document.media_type),
                    retrieved_at=COALESCE(excluded.retrieved_at,source_document.retrieved_at),
                    retrieval_method=COALESCE(excluded.retrieval_method,source_document.retrieval_method),
                    status=CASE
                        WHEN excluded.status='parsed' THEN 'parsed'
                        WHEN excluded.status='downloaded' AND source_document.status='metadata_only'
                            THEN 'downloaded'
                        ELSE source_document.status END,
                    raw_metadata_json=excluded.raw_metadata_json
                """,
                (
                    document_id,
                    issuer_id,
                    "sec_edgar",
                    metadata.accession_number,
                    metadata.form,
                    metadata.filing_date,
                    metadata.accepted_at,
                    available_at,
                    precision,
                    metadata.report_period,
                    metadata.accession_number,
                    metadata.primary_document,
                    metadata.source_url,
                    local_path,
                    content_hash,
                    media_type,
                    utc_now() if local_path else None,
                    retrieval_method,
                    status,
                    canonical_json(metadata.raw),
                ),
            )
        return document_id

    def replace_sections(
        self, document_id: str, sections: list[FilingSection], extractor_version: str
    ) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM filing_section WHERE document_id=?", (document_id,))
            conn.executemany(
                """
                INSERT INTO filing_section(
                    section_id,document_id,section_key,title,char_start,char_end,text,content_hash,
                    extractor_version
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        stable_id("section", document_id, item.key, sha256_text(item.text)),
                        document_id,
                        item.key,
                        item.title,
                        item.char_start,
                        item.char_end,
                        item.text,
                        sha256_text(item.text),
                        extractor_version,
                    )
                    for item in sections
                ],
            )
            conn.execute(
                "UPDATE source_document SET status='parsed' WHERE document_id=?", (document_id,)
            )

    def record_error(
        self,
        *,
        run_id: str,
        symbol: str,
        stage: str,
        source: str,
        error: Exception,
        retryable: bool,
        attempt: int = 1,
        context: dict[str, Any] | None = None,
    ) -> str:
        occurred_at = utc_now()
        error_id = stable_id(
            "error", run_id, symbol, stage, source, type(error).__name__, str(error), attempt
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ingestion_error(
                    error_id,run_id,symbol,stage,source,error_type,message,retryable,attempt,
                    occurred_at,context_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    error_id,
                    run_id,
                    symbol,
                    stage,
                    source,
                    type(error).__name__,
                    str(error),
                    int(retryable),
                    attempt,
                    occurred_at,
                    canonical_json(context or {}),
                ),
            )
        return error_id

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

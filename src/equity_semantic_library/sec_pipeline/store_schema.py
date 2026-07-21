from __future__ import annotations

SCHEMA_VERSION = 2

_SCHEMA = r"""
CREATE TABLE IF NOT EXISTS schema_migration(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pipeline_run(
    run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, completed_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('running','completed','partial','failed','cancelled')),
    config_json TEXT NOT NULL, source_metadata_path TEXT, source_metadata_sha256 TEXT,
    task_count INTEGER NOT NULL DEFAULT 0, completed_task_count INTEGER NOT NULL DEFAULT 0,
    failed_task_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS symbol_universe(
    symbol TEXT PRIMARY KEY, source_symbol TEXT, company_name TEXT, sector_code TEXT,
    industry_code TEXT, market_cap REAL, rank INTEGER, exchange TEXT, country TEXT,
    quote_type TEXT, security_type TEXT, is_etf INTEGER, source_path TEXT NOT NULL,
    source_row_hash TEXT NOT NULL, imported_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_symbol_universe_priority ON symbol_universe(market_cap DESC, rank ASC, symbol ASC);
CREATE TABLE IF NOT EXISTS issuer(
    issuer_id TEXT PRIMARY KEY, cik TEXT UNIQUE, legal_name TEXT, sic TEXT,
    sic_description TEXT, state_of_incorporation TEXT, country TEXT,
    identity_status TEXT NOT NULL, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS security(
    security_id TEXT PRIMARY KEY, issuer_id TEXT NOT NULL REFERENCES issuer(issuer_id),
    symbol TEXT NOT NULL UNIQUE, exchange TEXT, currency TEXT, status TEXT NOT NULL,
    first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_security_issuer ON security(issuer_id,symbol);
CREATE TABLE IF NOT EXISTS yahoo_profile_snapshot(
    snapshot_id TEXT PRIMARY KEY, security_id TEXT NOT NULL REFERENCES security(security_id),
    observed_at TEXT NOT NULL, available_at TEXT NOT NULL, payload_hash TEXT NOT NULL,
    market_cap INTEGER, enterprise_value INTEGER, sector_source TEXT, industry_source TEXT,
    business_summary TEXT, raw_json TEXT NOT NULL, UNIQUE(security_id,payload_hash)
);
CREATE TABLE IF NOT EXISTS filing(
    filing_id TEXT PRIMARY KEY, issuer_id TEXT NOT NULL REFERENCES issuer(issuer_id),
    security_id TEXT REFERENCES security(security_id), symbol TEXT NOT NULL, cik TEXT NOT NULL,
    accession TEXT NOT NULL UNIQUE, form TEXT NOT NULL, base_form TEXT NOT NULL,
    form_group TEXT NOT NULL, filing_date TEXT, report_date TEXT, accepted_at TEXT,
    available_at TEXT NOT NULL, available_at_precision TEXT NOT NULL, primary_document TEXT,
    source_url TEXT NOT NULL, raw_storage_uri TEXT, raw_sha256 TEXT, raw_bytes INTEGER,
    compressed_bytes INTEGER, retrieved_at TEXT, status TEXT NOT NULL, metadata_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_filing_symbol_form_time ON filing(symbol,base_form,available_at);
CREATE INDEX IF NOT EXISTS idx_filing_issuer_form_time ON filing(issuer_id,base_form,available_at);
CREATE TABLE IF NOT EXISTS filing_document(
    document_id TEXT PRIMARY KEY, filing_id TEXT NOT NULL REFERENCES filing(filing_id) ON DELETE CASCADE,
    sequence TEXT, document_type TEXT, filename TEXT, description TEXT, content_kind TEXT NOT NULL,
    mime_type TEXT, is_primary INTEGER NOT NULL, is_attachment INTEGER NOT NULL,
    source_start_byte INTEGER, source_end_byte INTEGER, raw_sha256 TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL, payload_bytes INTEGER NOT NULL, storage_uri TEXT
);
CREATE INDEX IF NOT EXISTS idx_filing_document_filing ON filing_document(filing_id);
CREATE TABLE IF NOT EXISTS filing_section(
    section_id TEXT PRIMARY KEY, filing_id TEXT NOT NULL REFERENCES filing(filing_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES filing_document(document_id) ON DELETE CASCADE,
    section_key TEXT NOT NULL, part TEXT, item TEXT, title TEXT, ordinal INTEGER NOT NULL,
    char_start INTEGER NOT NULL, char_end INTEGER NOT NULL, text TEXT NOT NULL,
    content_hash TEXT NOT NULL, extractor_version TEXT NOT NULL,
    UNIQUE(document_id,section_key,content_hash)
);
CREATE INDEX IF NOT EXISTS idx_filing_section_item ON filing_section(filing_id,item);
CREATE TABLE IF NOT EXISTS filing_table(
    table_id TEXT PRIMARY KEY, filing_id TEXT NOT NULL REFERENCES filing(filing_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES filing_document(document_id) ON DELETE CASCADE,
    section_hint TEXT, caption TEXT, row_count INTEGER NOT NULL, column_count INTEGER NOT NULL,
    rows_json TEXT NOT NULL, rows_hash TEXT NOT NULL, truncated INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS xbrl_fact(
    fact_id TEXT PRIMARY KEY, filing_id TEXT NOT NULL REFERENCES filing(filing_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES filing_document(document_id) ON DELETE CASCADE,
    concept TEXT NOT NULL, context_ref TEXT, unit_ref TEXT, decimals TEXT, scale TEXT,
    sign TEXT, is_nil TEXT, value TEXT, source_kind TEXT NOT NULL, fact_available_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_xbrl_fact_filing_concept ON xbrl_fact(filing_id,concept);
CREATE TABLE IF NOT EXISTS form13f_holding(
    holding_id TEXT PRIMARY KEY, filing_id TEXT NOT NULL REFERENCES filing(filing_id) ON DELETE CASCADE,
    issuer_name TEXT, class_title TEXT, cusip TEXT, figi TEXT, value_usd TEXT,
    shares_or_principal TEXT, share_type TEXT, put_call TEXT, investment_discretion TEXT,
    voting_sole TEXT, voting_shared TEXT, voting_none TEXT
);
CREATE TABLE IF NOT EXISTS event_ledger(
    event_id TEXT PRIMARY KEY, filing_id TEXT NOT NULL REFERENCES filing(filing_id) ON DELETE CASCADE,
    security_id TEXT REFERENCES security(security_id), symbol TEXT NOT NULL, event_type TEXT NOT NULL,
    item TEXT, event_time TEXT NOT NULL, event_time_precision TEXT NOT NULL, title TEXT,
    payload_json TEXT NOT NULL, confidence REAL NOT NULL, extractor_version TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_symbol_time ON event_ledger(symbol,event_time);
CREATE TABLE IF NOT EXISTS evidence_snippet(
    evidence_id TEXT PRIMARY KEY, filing_id TEXT NOT NULL REFERENCES filing(filing_id) ON DELETE CASCADE,
    document_id TEXT REFERENCES filing_document(document_id), section_id TEXT REFERENCES filing_section(section_id),
    source_sha256 TEXT NOT NULL, snippet TEXT NOT NULL, snippet_hash TEXT NOT NULL,
    char_start INTEGER, char_end INTEGER, accepted_at TEXT, available_at TEXT NOT NULL,
    observed_at TEXT NOT NULL, extractor_version TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_filing_time ON evidence_snippet(filing_id,available_at);
CREATE TABLE IF NOT EXISTS semantic_assertion(
    assertion_id TEXT PRIMARY KEY, security_id TEXT REFERENCES security(security_id),
    filing_id TEXT NOT NULL REFERENCES filing(filing_id) ON DELETE CASCADE,
    section_id TEXT REFERENCES filing_section(section_id),
    evidence_id TEXT NOT NULL REFERENCES evidence_snippet(evidence_id), assertion_type TEXT NOT NULL,
    subject_key TEXT NOT NULL, predicate TEXT NOT NULL, object_json TEXT NOT NULL,
    confidence REAL NOT NULL, explicitness TEXT NOT NULL CHECK(explicitness IN ('explicit','estimated','inferred')),
    status TEXT NOT NULL CHECK(status IN ('accepted','review_required','rejected','superseded')),
    available_at TEXT NOT NULL, effective_from TEXT, effective_to TEXT, extractor_id TEXT NOT NULL,
    extractor_version TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assertion_subject_time ON semantic_assertion(subject_key,predicate,available_at);
CREATE INDEX IF NOT EXISTS idx_assertion_filing_status ON semantic_assertion(filing_id,status,assertion_type);
CREATE INDEX IF NOT EXISTS idx_assertion_evidence ON semantic_assertion(evidence_id);
CREATE TABLE IF NOT EXISTS company_relation(
    relation_id TEXT PRIMARY KEY, source_issuer_id TEXT NOT NULL REFERENCES issuer(issuer_id),
    target_entity_key TEXT NOT NULL, target_ticker TEXT, relation_type TEXT NOT NULL,
    product_scope TEXT, filing_id TEXT NOT NULL REFERENCES filing(filing_id),
    section_id TEXT REFERENCES filing_section(section_id),
    evidence_id TEXT NOT NULL REFERENCES evidence_snippet(evidence_id), confidence REAL NOT NULL,
    explicitness TEXT NOT NULL, status TEXT NOT NULL, available_at TEXT NOT NULL,
    effective_from TEXT, effective_to TEXT, extractor_version TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_relation_source_time ON company_relation(source_issuer_id,relation_type,available_at);
CREATE INDEX IF NOT EXISTS idx_relation_target_time ON company_relation(target_ticker,relation_type,available_at);
CREATE TABLE IF NOT EXISTS section_semantic_context(
    section_id TEXT PRIMARY KEY REFERENCES filing_section(section_id) ON DELETE CASCADE,
    filing_id TEXT NOT NULL REFERENCES filing(filing_id) ON DELETE CASCADE,
    form TEXT NOT NULL, form_group TEXT NOT NULL, section_role TEXT NOT NULL,
    issuer_scope TEXT NOT NULL CHECK(issuer_scope IN ('issuer','third_party','mixed','unknown')),
    allow_topic_promotion INTEGER NOT NULL, allow_concept_promotion INTEGER NOT NULL,
    allow_relation_promotion INTEGER NOT NULL, classifier_version TEXT NOT NULL,
    reasons_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_section_context_role ON section_semantic_context(filing_id,section_role);
CREATE TABLE IF NOT EXISTS semantic_candidate(
    candidate_id TEXT PRIMARY KEY,
    issuer_id TEXT NOT NULL REFERENCES issuer(issuer_id),
    security_id TEXT REFERENCES security(security_id),
    filing_id TEXT NOT NULL REFERENCES filing(filing_id) ON DELETE CASCADE,
    section_id TEXT REFERENCES filing_section(section_id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES evidence_snippet(evidence_id) ON DELETE CASCADE,
    candidate_type TEXT NOT NULL, predicate TEXT NOT NULL, object_json TEXT NOT NULL,
    confidence REAL NOT NULL,
    explicitness TEXT NOT NULL CHECK(explicitness IN ('structured','explicit','lexical','inferred')),
    status TEXT NOT NULL CHECK(status IN ('pending','rule_accepted','review_required','review_accepted','rejected','superseded')),
    promotion_level TEXT NOT NULL CHECK(promotion_level IN ('A','B','C','D','R')),
    form TEXT NOT NULL, section_role TEXT NOT NULL, rule_id TEXT NOT NULL,
    rule_version TEXT NOT NULL, subject_binding TEXT NOT NULL,
    polarity TEXT NOT NULL, modality TEXT NOT NULL, rejection_reason TEXT,
    available_at TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(evidence_id,predicate,object_json,rule_id)
);
CREATE INDEX IF NOT EXISTS idx_candidate_review_queue ON semantic_candidate(status,promotion_level,available_at);
CREATE INDEX IF NOT EXISTS idx_candidate_filing ON semantic_candidate(filing_id,candidate_type,status);
CREATE TABLE IF NOT EXISTS semantic_review(
    review_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL,
    candidate_snapshot_json TEXT NOT NULL,
    reviewer_type TEXT NOT NULL CHECK(reviewer_type IN ('llm','human','rule')),
    reviewer_id TEXT NOT NULL, reviewer_version TEXT,
    decision TEXT NOT NULL CHECK(decision IN ('accept','reject','change','ambiguous')),
    corrected_predicate TEXT, corrected_object_json TEXT, rationale TEXT NOT NULL,
    input_hash TEXT NOT NULL, reviewed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_review_candidate_time ON semantic_review(candidate_id,reviewed_at);
CREATE TABLE IF NOT EXISTS candidate_promotion(
    promotion_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL,
    assertion_id TEXT REFERENCES semantic_assertion(assertion_id) ON DELETE SET NULL,
    relation_id TEXT REFERENCES company_relation(relation_id) ON DELETE SET NULL,
    method TEXT NOT NULL, review_id TEXT, promoted_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_promotion_candidate ON candidate_promotion(candidate_id,promoted_at);
CREATE TABLE IF NOT EXISTS dag_task(
    task_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES pipeline_run(run_id) ON DELETE CASCADE,
    task_type TEXT NOT NULL, lane TEXT NOT NULL, priority INTEGER NOT NULL, symbol TEXT, cik TEXT,
    accession TEXT, form TEXT, payload_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending','running','completed','failed','skipped','cancelled')),
    attempt_count INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL, not_before TEXT,
    lease_owner TEXT, lease_expires_at TEXT, last_error TEXT, created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL, completed_at TEXT, UNIQUE(run_id,task_type,symbol,accession)
);
CREATE INDEX IF NOT EXISTS idx_dag_task_ready ON dag_task(run_id,lane,status,priority,not_before);
CREATE TABLE IF NOT EXISTS dag_dependency(
    task_id TEXT NOT NULL REFERENCES dag_task(task_id) ON DELETE CASCADE,
    depends_on_task_id TEXT NOT NULL REFERENCES dag_task(task_id) ON DELETE CASCADE,
    PRIMARY KEY(task_id,depends_on_task_id)
);
CREATE TABLE IF NOT EXISTS dag_event(
    event_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, task_id TEXT,
    occurred_at TEXT NOT NULL, event_type TEXT NOT NULL, worker_id TEXT, payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pipeline_issue(
    issue_id TEXT PRIMARY KEY, run_id TEXT, task_id TEXT, symbol TEXT, accession TEXT,
    stage TEXT NOT NULL, severity TEXT NOT NULL, code TEXT NOT NULL, message TEXT NOT NULL,
    context_json TEXT NOT NULL, occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS filing_overflow(
    overflow_id TEXT PRIMARY KEY, run_id TEXT, issuer_id TEXT REFERENCES issuer(issuer_id),
    symbol TEXT NOT NULL, cik TEXT NOT NULL, accession TEXT NOT NULL, form TEXT NOT NULL,
    base_form TEXT NOT NULL, form_group TEXT NOT NULL, filing_date TEXT, report_date TEXT,
    accepted_at TEXT, available_at TEXT NOT NULL, available_at_precision TEXT NOT NULL,
    primary_document TEXT, source_url TEXT, metadata_json TEXT NOT NULL,
    reason TEXT NOT NULL, discovered_at TEXT NOT NULL, UNIQUE(run_id,accession)
);
CREATE INDEX IF NOT EXISTS idx_filing_overflow_symbol ON filing_overflow(symbol,available_at);
CREATE VIEW IF NOT EXISTS security_filing AS
SELECT s.security_id AS query_security_id, s.symbol AS query_symbol, f.*
FROM security s JOIN filing f ON f.issuer_id=s.issuer_id;
CREATE VIEW IF NOT EXISTS security_semantic_assertion AS
SELECT s.security_id AS query_security_id, s.symbol AS query_symbol, a.*
FROM security s
JOIN filing f ON f.issuer_id=s.issuer_id
JOIN semantic_assertion a ON a.filing_id=f.filing_id
WHERE a.security_id IS NULL OR a.security_id=s.security_id;
CREATE VIEW IF NOT EXISTS security_company_relation AS
SELECT s.security_id AS query_security_id, s.symbol AS query_symbol, r.*
FROM security s JOIN company_relation r ON r.source_issuer_id=s.issuer_id;
CREATE VIEW IF NOT EXISTS security_event_ledger AS
SELECT s.security_id AS query_security_id, s.symbol AS query_symbol, e.*
FROM security s
JOIN filing f ON f.issuer_id=s.issuer_id
JOIN event_ledger e ON e.filing_id=f.filing_id;
"""

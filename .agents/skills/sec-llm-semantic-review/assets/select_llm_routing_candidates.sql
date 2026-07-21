-- SEC/Yfinance structured database
-- Promotion-aware, read-only LLM routing queries.
-- Run one query at a time. The scheduler must freeze :signal_timestamp.
--
-- IMPORTANT:
--   A is never selected.
--   B is an audit population; sample deterministically outside SQL.
--   C is mandatory by evidence group.
--   D is grouped by evidence_id/sentence before review.
--   R requires a retained rejection-audit table and is sampled by rule version.

-- ===========================================================================
-- 1. C mandatory review: ambiguous assertions grouped by evidence sentence.
-- One evidence item is one LLM request even when it generated many candidates.
-- ===========================================================================
SELECT
    'C' AS promotion_level,
    'mandatory' AS llm_route,
    f.issuer_id || '|' || f.filing_id || '|' || COALESCE(a.section_id, '') || '|'
        || a.evidence_id AS evidence_group_key_material,
    f.security_id,
    f.issuer_id,
    f.symbol,
    f.filing_id,
    f.accession,
    f.form,
    f.base_form,
    f.form_group,
    f.available_at,
    f.available_at_precision,
    a.section_id,
    a.evidence_id AS primary_evidence_id,
    GROUP_CONCAT(a.assertion_id) AS candidate_ids,
    GROUP_CONCAT(DISTINCT a.assertion_type) AS candidate_types,
    GROUP_CONCAT(DISTINCT a.predicate) AS candidate_predicates,
    GROUP_CONCAT(a.object_json, '\n---candidate---\n') AS candidate_objects,
    MIN(a.confidence) AS minimum_legacy_confidence,
    GROUP_CONCAT(DISTINCT a.explicitness) AS explicitness_values,
    e.snippet,
    e.source_sha256
FROM semantic_assertion AS a
JOIN filing AS f ON f.filing_id = a.filing_id
JOIN evidence_snippet AS e ON e.evidence_id = a.evidence_id
WHERE
    f.available_at <= :signal_timestamp
    AND (
        a.status = 'review_required'
        OR a.explicitness IN ('estimated', 'inferred')
        OR a.assertion_type IN (
            'risk',
            'potential_event',
            'management_interpretation',
            'relation_candidate'
        )
        OR lower(a.predicate) GLOB '*potential*'
        OR lower(a.predicate) GLOB '*risk*'
        OR lower(a.predicate) GLOB '*expect*'
    )
GROUP BY
    f.security_id, f.issuer_id, f.symbol, f.filing_id, f.accession,
    f.form, f.base_form, f.form_group, f.available_at,
    f.available_at_precision, a.section_id, a.evidence_id,
    e.snippet, e.source_sha256
ORDER BY f.available_at, f.symbol, a.evidence_id;

-- ===========================================================================
-- 2. B audit population: explicit admitted relations.
-- Do NOT send this entire result to the LLM. Apply replayable stratified
-- sampling (normally 1%-5%; higher for high-impact relation families).
-- ===========================================================================
SELECT
    'B' AS promotion_level,
    'sampled_audit' AS llm_route,
    f.issuer_id || '|' || f.filing_id || '|' || COALESCE(r.section_id, '') || '|'
        || r.evidence_id AS evidence_group_key_material,
    f.security_id,
    r.source_issuer_id AS issuer_id,
    f.symbol,
    f.filing_id,
    f.accession,
    f.form,
    f.base_form,
    f.form_group,
    f.available_at,
    f.available_at_precision,
    r.section_id,
    r.evidence_id AS primary_evidence_id,
    GROUP_CONCAT(r.relation_id) AS candidate_ids,
    GROUP_CONCAT(DISTINCT r.target_entity_key) AS target_entities,
    GROUP_CONCAT(DISTINCT r.target_ticker) AS target_tickers,
    GROUP_CONCAT(DISTINCT r.relation_type) AS relation_types,
    GROUP_CONCAT(DISTINCT r.product_scope) AS product_scopes,
    MIN(r.confidence) AS minimum_legacy_confidence,
    GROUP_CONCAT(DISTINCT r.explicitness) AS explicitness_values,
    e.snippet,
    e.source_sha256,
    CASE
        WHEN r.relation_type IN (
            'customer_of',
            'supplier_for',
            'foundry_for',
            'memory_supplier_for',
            'strategic_investment_in',
            'restricted_by',
            'competes_with'
        ) THEN 'high_impact_relation'
        ELSE 'normal_rule_audit'
    END AS sample_stratum
FROM company_relation AS r
JOIN filing AS f ON f.filing_id = r.filing_id
JOIN evidence_snippet AS e ON e.evidence_id = r.evidence_id
WHERE
    f.available_at <= :signal_timestamp
    AND r.status = 'accepted'
    AND r.explicitness = 'explicit'
    AND r.confidence >= 0.90
GROUP BY
    f.security_id, r.source_issuer_id, f.symbol, f.filing_id, f.accession,
    f.form, f.base_form, f.form_group, f.available_at,
    f.available_at_precision, r.section_id, r.evidence_id,
    e.snippet, e.source_sha256, sample_stratum
ORDER BY sample_stratum DESC, f.available_at, f.symbol, r.evidence_id;

-- ===========================================================================
-- 3. D external-company mention groups.
-- Assumes company mentions are retained as semantic assertions using either
-- assertion_type='external_company_mention' or predicate='company_mention'.
-- One evidence_id produces one request containing every entity/topic candidate.
-- ===========================================================================
WITH mention_rows AS (
    SELECT
        a.assertion_id,
        a.security_id,
        f.issuer_id,
        f.symbol,
        f.filing_id,
        f.accession,
        f.form,
        f.base_form,
        f.form_group,
        f.report_date,
        f.available_at,
        f.available_at_precision,
        a.section_id,
        s.item,
        s.title,
        a.evidence_id,
        a.predicate,
        a.object_json,
        e.snippet,
        e.source_sha256,
        CASE
            WHEN f.base_form = '10-K' AND (
                s.item IN ('1', '1A', '7')
                OR lower(COALESCE(s.title, '')) GLOB '*business*'
                OR lower(COALESCE(s.title, '')) GLOB '*risk*'
                OR lower(COALESCE(s.title, '')) GLOB '*management*discussion*'
            ) THEN 'high_value_section'
            WHEN f.base_form = '10-Q' AND (
                lower(COALESCE(s.title, '')) GLOB '*risk*'
                OR lower(COALESCE(s.title, '')) GLOB '*management*discussion*'
            ) THEN 'high_value_section'
            WHEN lower(COALESCE(s.title, '')) GLOB '*biograph*'
              OR lower(COALESCE(s.title, '')) GLOB '*underwriter*'
              OR lower(COALESCE(s.title, '')) GLOB '*definition*'
              OR lower(COALESCE(s.title, '')) GLOB '*signature*'
              OR lower(COALESCE(s.title, '')) GLOB '*trademark*'
            THEN 'low_value_section'
            ELSE 'other_section'
        END AS section_value,
        CASE
            WHEN lower(e.snippet) GLOB '* supplier*'
              OR lower(e.snippet) GLOB '* customer*'
              OR lower(e.snippet) GLOB '* competitor*'
              OR lower(e.snippet) GLOB '* foundry*'
              OR lower(e.snippet) GLOB '* manufacture*'
              OR lower(e.snippet) GLOB '* purchase*'
              OR lower(e.snippet) GLOB '* sell*'
              OR lower(e.snippet) GLOB '* distribut*'
              OR lower(e.snippet) GLOB '* collaborat*'
              OR lower(e.snippet) GLOB '* partner*'
              OR lower(e.snippet) GLOB '* invest*'
              OR lower(e.snippet) GLOB '* licens*'
            THEN 1 ELSE 0
        END AS has_financial_action,
        CASE
            WHEN lower(e.snippet) GLOB '* we *'
              OR lower(e.snippet) GLOB '* our *'
              OR lower(e.snippet) GLOB '*the company*'
            THEN 1 ELSE 0
        END AS has_issuer_voice,
        CASE
            WHEN e.snippet GLOB '*[0-9]%*'
              OR e.snippet GLOB '*$[0-9]*'
              OR e.snippet GLOB '*[0-9] million*'
              OR e.snippet GLOB '*[0-9] billion*'
            THEN 1 ELSE 0
        END AS has_quantified_context
    FROM semantic_assertion AS a
    JOIN filing AS f ON f.filing_id = a.filing_id
    JOIN evidence_snippet AS e ON e.evidence_id = a.evidence_id
    LEFT JOIN filing_section AS s ON s.section_id = a.section_id
    WHERE
        f.available_at <= :signal_timestamp
        AND (
            a.assertion_type = 'external_company_mention'
            OR a.predicate = 'company_mention'
        )
), grouped AS (
    SELECT
        security_id,
        issuer_id,
        symbol,
        filing_id,
        accession,
        form,
        base_form,
        form_group,
        report_date,
        available_at,
        available_at_precision,
        section_id,
        item,
        title,
        evidence_id,
        snippet,
        source_sha256,
        MAX(section_value = 'high_value_section') AS high_value_section,
        MAX(section_value = 'low_value_section') AS low_value_section,
        MAX(has_financial_action) AS has_financial_action,
        MAX(has_issuer_voice) AS has_issuer_voice,
        MAX(has_quantified_context) AS has_quantified_context,
        GROUP_CONCAT(assertion_id) AS candidate_ids,
        GROUP_CONCAT(DISTINCT predicate) AS candidate_predicates,
        GROUP_CONCAT(object_json, '\n---candidate---\n') AS candidate_objects
    FROM mention_rows
    GROUP BY
        security_id, issuer_id, symbol, filing_id, accession, form,
        base_form, form_group, report_date, available_at,
        available_at_precision, section_id, item, title, evidence_id,
        snippet, source_sha256
)
SELECT
    CASE
        WHEN low_value_section = 1
            THEN 'D3'
        WHEN high_value_section = 1
          OR has_financial_action = 1
          OR has_issuer_voice = 1
          OR has_quantified_context = 1
            THEN 'D1'
        ELSE 'D2'
    END AS promotion_level,
    CASE
        WHEN low_value_section = 1
            THEN 'no_default_review'
        WHEN high_value_section = 1
          OR has_financial_action = 1
          OR has_issuer_voice = 1
          OR has_quantified_context = 1
            THEN 'grouped_mandatory'
        ELSE 'aggregate_then_review'
    END AS llm_route,
    issuer_id || '|' || filing_id || '|' || COALESCE(section_id, '') || '|'
        || evidence_id AS evidence_group_key_material,
    issuer_id || '|' || COALESCE(title, '') || '|' || evidence_id || '|'
        || COALESCE(substr(report_date, 1, 7), '') AS d2_dedupe_key_material,
    security_id,
    issuer_id,
    symbol,
    filing_id,
    accession,
    form,
    base_form,
    form_group,
    report_date,
    available_at,
    available_at_precision,
    section_id,
    item,
    title,
    evidence_id AS primary_evidence_id,
    candidate_ids,
    candidate_predicates,
    candidate_objects,
    snippet,
    source_sha256,
    high_value_section,
    has_financial_action,
    has_issuer_voice,
    has_quantified_context
FROM grouped
ORDER BY
    CASE promotion_level WHEN 'D1' THEN 1 WHEN 'D2' THEN 2 ELSE 3 END,
    available_at,
    symbol,
    evidence_id;

-- ===========================================================================
-- 4. R rejection audit template.
-- This query is intentionally commented because current deployments may not
-- yet retain a rejected_semantic_candidate table. When implemented, retain
-- rejection rows and sample deterministically by rule_id + rule_version.
-- ===========================================================================
-- SELECT
--     'R' AS promotion_level,
--     'rejection_audit' AS llm_route,
--     rule_id,
--     rule_version,
--     rejection_reason,
--     evidence_id AS primary_evidence_id,
--     candidate_id,
--     source_available_at
-- FROM rejected_semantic_candidate
-- WHERE source_available_at <= :signal_timestamp
-- ORDER BY rule_id, rule_version, candidate_id;

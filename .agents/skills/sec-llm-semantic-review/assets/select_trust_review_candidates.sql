-- SEC/Yfinance structured database
-- Read-only candidate queries for multidimensional trust-semantic review.
-- Run one query at a time and freeze :signal_timestamp before materialization.

-- ---------------------------------------------------------------------------
-- 1. Default trust-profile reconstruction queue.
-- Existing confidence is not interpreted as truth; it is only an old routing
-- signal. The LLM must produce the full trust_profile.
-- ---------------------------------------------------------------------------
SELECT
    'trust_profile_reconstruction' AS candidate_reason,
    a.assertion_id,
    NULL AS relation_id,
    a.security_id,
    f.issuer_id,
    f.symbol,
    f.filing_id,
    f.accession,
    f.form,
    f.base_form,
    f.form_group,
    f.accepted_at,
    f.available_at,
    f.available_at_precision,
    a.section_id,
    a.evidence_id,
    a.assertion_type,
    a.predicate,
    a.object_json,
    a.confidence AS legacy_confidence,
    a.explicitness,
    a.status,
    e.snippet,
    e.source_sha256,
    e.char_start,
    e.char_end
FROM semantic_assertion AS a
JOIN filing AS f ON f.filing_id = a.filing_id
JOIN evidence_snippet AS e ON e.evidence_id = a.evidence_id
WHERE
    f.available_at <= :signal_timestamp
    AND (
        a.status = 'review_required'
        OR a.explicitness IN ('estimated', 'inferred')
        OR a.assertion_type IN ('risk', 'potential_event', 'management_interpretation')
        OR lower(a.predicate) GLOB '*potential*'
        OR lower(a.predicate) GLOB '*risk*'
        OR lower(a.predicate) GLOB '*expect*'
    )
ORDER BY f.available_at, f.symbol, a.assertion_id;

-- ---------------------------------------------------------------------------
-- 2. Attribution ambiguity: one snippet contains language from multiple
-- epistemic classes. Patterns are routing hints, never automatic conclusions.
-- ---------------------------------------------------------------------------
SELECT
    'attribution_ambiguity' AS candidate_reason,
    f.security_id,
    f.issuer_id,
    f.symbol,
    f.filing_id,
    f.accession,
    f.form,
    f.available_at,
    f.available_at_precision,
    e.section_id,
    e.evidence_id,
    e.snippet,
    e.source_sha256,
    CASE
        WHEN lower(e.snippet) GLOB '*we expect*' OR lower(e.snippet) GLOB '*we anticipate*'
            THEN 'management_estimate_language'
        WHEN lower(e.snippet) GLOB '*we believe*' OR lower(e.snippet) GLOB '*we attribute*'
            THEN 'management_interpretation_language'
        WHEN lower(e.snippet) GLOB '*according to*' OR lower(e.snippet) GLOB '*informed us*'
            THEN 'third_party_attribution_language'
        WHEN lower(e.snippet) GLOB '*alleged*' OR lower(e.snippet) GLOB '*complaint*'
            THEN 'legal_allegation_language'
        ELSE 'mixed_attribution_language'
    END AS routing_hint
FROM evidence_snippet AS e
JOIN filing AS f ON f.filing_id = e.filing_id
WHERE
    f.available_at <= :signal_timestamp
    AND (
        lower(e.snippet) GLOB '*we expect*'
        OR lower(e.snippet) GLOB '*we anticipate*'
        OR lower(e.snippet) GLOB '*we believe*'
        OR lower(e.snippet) GLOB '*we attribute*'
        OR lower(e.snippet) GLOB '*according to*'
        OR lower(e.snippet) GLOB '*informed us*'
        OR lower(e.snippet) GLOB '*alleged*'
        OR lower(e.snippet) GLOB '*complaint*'
    )
ORDER BY f.available_at, f.symbol, e.evidence_id;

-- ---------------------------------------------------------------------------
-- 3. Inference audit for named relations. A generic deterministic relation may
-- be explicit while role, direction, or product scope remains unsupported.
-- ---------------------------------------------------------------------------
SELECT
    CASE
        WHEN r.product_scope IS NULL OR trim(r.product_scope) = ''
            THEN 'relation_scope_missing'
        ELSE 'inference_audit'
    END AS candidate_reason,
    NULL AS assertion_id,
    r.relation_id,
    f.security_id,
    r.source_issuer_id AS issuer_id,
    f.symbol,
    f.filing_id,
    f.accession,
    f.form,
    f.available_at,
    f.available_at_precision,
    r.section_id,
    r.evidence_id,
    r.target_entity_key,
    r.target_ticker,
    r.relation_type,
    r.product_scope,
    r.confidence AS legacy_confidence,
    r.explicitness,
    r.status,
    e.snippet,
    e.source_sha256
FROM company_relation AS r
JOIN filing AS f ON f.filing_id = r.filing_id
JOIN evidence_snippet AS e ON e.evidence_id = r.evidence_id
WHERE
    f.available_at <= :signal_timestamp
    AND (
        r.status = 'review_required'
        OR r.product_scope IS NULL
        OR trim(r.product_scope) = ''
        OR r.relation_type IN (
            'supplier_or_manufacturer',
            'customer_or_channel',
            'partner_or_collaborator',
            'investment_or_holding'
        )
        OR r.explicitness = 'inferred'
    )
ORDER BY f.available_at, f.symbol, r.relation_id;

-- ---------------------------------------------------------------------------
-- 4. Potential-event and realized-event separation. Modal words are candidate
-- signals only. They do not provide an event probability.
-- ---------------------------------------------------------------------------
SELECT
    'potential_future_event' AS candidate_reason,
    f.security_id,
    f.issuer_id,
    f.symbol,
    f.filing_id,
    f.accession,
    f.form,
    f.available_at,
    f.available_at_precision,
    e.section_id,
    e.evidence_id,
    e.snippet,
    e.source_sha256
FROM evidence_snippet AS e
JOIN filing AS f ON f.filing_id = e.filing_id
WHERE
    f.available_at <= :signal_timestamp
    AND (
        lower(e.snippet) GLOB '* may *'
        OR lower(e.snippet) GLOB '* could *'
        OR lower(e.snippet) GLOB '* expects *'
        OR lower(e.snippet) GLOB '* expected *'
        OR lower(e.snippet) GLOB '* plans *'
        OR lower(e.snippet) GLOB '* intends *'
        OR lower(e.snippet) GLOB '* subject to *'
        OR lower(e.snippet) GLOB '* depends on *'
        OR lower(e.snippet) GLOB '* up to *'
    )
ORDER BY f.available_at, f.symbol, e.evidence_id;

-- ---------------------------------------------------------------------------
-- 5. Possible non-independent corroboration. Several assertions tied to one
-- evidence item must not be counted as several independent sources.
-- ---------------------------------------------------------------------------
SELECT
    'inference_audit' AS candidate_reason,
    a.evidence_id,
    f.symbol,
    f.filing_id,
    f.accession,
    f.form,
    f.available_at,
    COUNT(*) AS assertion_count,
    GROUP_CONCAT(a.assertion_id) AS assertion_ids,
    GROUP_CONCAT(a.predicate) AS predicates,
    e.snippet,
    e.source_sha256
FROM semantic_assertion AS a
JOIN filing AS f ON f.filing_id = a.filing_id
JOIN evidence_snippet AS e ON e.evidence_id = a.evidence_id
WHERE f.available_at <= :signal_timestamp
GROUP BY a.evidence_id, f.symbol, f.filing_id, f.accession, f.form,
         f.available_at, e.snippet, e.source_sha256
HAVING COUNT(*) > 1
ORDER BY assertion_count DESC, f.available_at, f.symbol;

-- ---------------------------------------------------------------------------
-- 6. Comparable disclosure pairs for contradiction/supersession review.
-- Bind :symbol, :base_form, and :signal_timestamp. Absence is not removal.
-- ---------------------------------------------------------------------------
WITH eligible AS (
    SELECT
        f.filing_id,
        f.symbol,
        f.base_form,
        f.report_date,
        f.available_at,
        s.section_id,
        s.item,
        s.section_key,
        s.title,
        s.text,
        ROW_NUMBER() OVER (
            PARTITION BY f.symbol, f.base_form, COALESCE(s.item, s.section_key)
            ORDER BY f.available_at DESC
        ) AS recency
    FROM filing AS f
    JOIN filing_section AS s ON s.filing_id = f.filing_id
    WHERE
        f.symbol = :symbol
        AND f.base_form = :base_form
        AND f.available_at <= :signal_timestamp
)
SELECT
    'contradiction_review' AS candidate_reason,
    current.symbol,
    current.base_form,
    current.filing_id AS current_filing_id,
    current.available_at AS current_available_at,
    current.section_id AS current_section_id,
    prior.filing_id AS prior_filing_id,
    prior.available_at AS prior_available_at,
    prior.section_id AS prior_section_id,
    COALESCE(current.item, current.section_key) AS comparison_key,
    current.title AS current_title,
    prior.title AS prior_title,
    current.text AS current_text,
    prior.text AS prior_text
FROM eligible AS current
JOIN eligible AS prior
  ON prior.symbol = current.symbol
 AND prior.base_form = current.base_form
 AND COALESCE(prior.item, prior.section_key) = COALESCE(current.item, current.section_key)
 AND current.recency = 1
 AND prior.recency = 2
ORDER BY comparison_key;

-- ---------------------------------------------------------------------------
-- 7. 13F normalization only. Do not infer transaction timing, purchase price,
-- strategic intent, partnership, control, endorsement, or commercial links.
-- ---------------------------------------------------------------------------
SELECT
    'attribution_ambiguity' AS candidate_reason,
    f.symbol AS reporting_manager_symbol,
    f.filing_id,
    f.accession,
    f.report_date,
    f.available_at,
    h.holding_id,
    h.issuer_name,
    h.class_title,
    h.cusip,
    h.figi,
    h.value_usd,
    h.shares_or_principal,
    h.share_type
FROM form13f_holding AS h
JOIN filing AS f ON f.filing_id = h.filing_id
WHERE
    f.available_at <= :signal_timestamp
    AND (
        h.issuer_name IS NULL
        OR trim(h.issuer_name) = ''
        OR h.cusip IS NULL
        OR trim(h.cusip) = ''
        OR h.issuer_name GLOB '*  *'
    )
ORDER BY f.available_at, f.symbol, h.holding_id;

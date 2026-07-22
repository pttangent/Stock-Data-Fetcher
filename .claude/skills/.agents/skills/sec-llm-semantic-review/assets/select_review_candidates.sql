-- SEC/Yfinance structured database
-- Select only records that may require post-processing LLM semantic review.
-- These queries do not modify the database.

-- ---------------------------------------------------------------------------
-- 1. Existing deterministic assertions already routed for review or carrying
--    estimated/inferred meaning. This is the default review queue.
-- ---------------------------------------------------------------------------
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
    f.accepted_at,
    f.available_at,
    f.available_at_precision,
    a.section_id,
    a.evidence_id,
    a.assertion_type,
    a.predicate,
    a.object_json,
    a.confidence,
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
    a.status = 'review_required'
    OR a.explicitness IN ('estimated', 'inferred')
    OR a.confidence < 0.90
ORDER BY f.available_at, f.symbol, a.assertion_id;

-- ---------------------------------------------------------------------------
-- 2. Generic company relations whose role or product scope may need refinement.
--    Do not automatically accept the LLM refinement.
-- ---------------------------------------------------------------------------
SELECT
    r.relation_id,
    f.security_id,
    r.source_issuer_id,
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
    r.confidence,
    r.explicitness,
    r.status,
    e.snippet,
    e.source_sha256
FROM company_relation AS r
JOIN filing AS f ON f.filing_id = r.filing_id
JOIN evidence_snippet AS e ON e.evidence_id = r.evidence_id
WHERE
    r.status = 'review_required'
    OR r.relation_type IN (
        'supplier_or_manufacturer',
        'customer_or_channel',
        'partner_or_collaborator',
        'investment_or_holding'
    )
    OR r.product_scope IS NULL
    OR r.confidence < 0.90
ORDER BY f.available_at, f.symbol, r.relation_id;

-- ---------------------------------------------------------------------------
-- 3. Product lifecycle language. Restrict this queue to known product evidence
--    where state words coexist with a product or platform mention.
-- ---------------------------------------------------------------------------
SELECT DISTINCT
    f.security_id,
    f.issuer_id,
    f.symbol,
    f.filing_id,
    f.accession,
    f.form,
    f.available_at,
    f.available_at_precision,
    s.section_id,
    s.item,
    s.title,
    e.evidence_id,
    e.snippet,
    e.source_sha256
FROM filing AS f
JOIN filing_section AS s ON s.filing_id = f.filing_id
JOIN evidence_snippet AS e ON e.section_id = s.section_id
WHERE
    lower(e.snippet) GLOB '*hbm3e*'
    OR lower(e.snippet) GLOB '*hbm4*'
    OR lower(e.snippet) GLOB '*mi300*'
    OR lower(e.snippet) GLOB '*mi308*'
    OR lower(e.snippet) GLOB '*mi350*'
    OR lower(e.snippet) GLOB '*blackwell*'
    OR lower(e.snippet) GLOB '*vmware cloud foundation*'
    OR lower(e.snippet) GLOB '*llama*'
INTERSECT
SELECT DISTINCT
    f.security_id,
    f.issuer_id,
    f.symbol,
    f.filing_id,
    f.accession,
    f.form,
    f.available_at,
    f.available_at_precision,
    s.section_id,
    s.item,
    s.title,
    e.evidence_id,
    e.snippet,
    e.source_sha256
FROM filing AS f
JOIN filing_section AS s ON s.filing_id = f.filing_id
JOIN evidence_snippet AS e ON e.section_id = s.section_id
WHERE
    lower(e.snippet) GLOB '*sample*'
    OR lower(e.snippet) GLOB '*volume production*'
    OR lower(e.snippet) GLOB '*began shipping*'
    OR lower(e.snippet) GLOB '*qualified*'
    OR lower(e.snippet) GLOB '*ramp*'
    OR lower(e.snippet) GLOB '*roadmap*'
    OR lower(e.snippet) GLOB '*majority of*shipments*'
ORDER BY available_at, symbol, evidence_id;

-- ---------------------------------------------------------------------------
-- 4. Mixed financial claim classes in one evidence window. These patterns flag
--    actual/estimate/risk decomposition tasks; they are not facts by themselves.
-- ---------------------------------------------------------------------------
SELECT
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
        WHEN lower(e.snippet) GLOB '*expected*' AND lower(e.snippet) GLOB '*recorded*'
            THEN 'estimate_and_actual'
        WHEN lower(e.snippet) GLOB '*incurred*' AND lower(e.snippet) GLOB '*could*'
            THEN 'actual_and_risk'
        WHEN lower(e.snippet) GLOB '*license*' AND lower(e.snippet) GLOB '*depend*'
            THEN 'rule_and_conditional_exposure'
        WHEN lower(e.snippet) GLOB '*target*' AND lower(e.snippet) GLOB '*revenue*'
            THEN 'target_metric_not_actual_revenue'
        ELSE 'mixed_claim_candidate'
    END AS review_reason
FROM evidence_snippet AS e
JOIN filing AS f ON f.filing_id = e.filing_id
WHERE
    (lower(e.snippet) GLOB '*expected*' AND lower(e.snippet) GLOB '*recorded*')
    OR (lower(e.snippet) GLOB '*incurred*' AND lower(e.snippet) GLOB '*could*')
    OR (lower(e.snippet) GLOB '*license*' AND lower(e.snippet) GLOB '*depend*')
    OR (lower(e.snippet) GLOB '*target*' AND lower(e.snippet) GLOB '*revenue*')
ORDER BY f.available_at, f.symbol, e.evidence_id;

-- ---------------------------------------------------------------------------
-- 5. Segment and accounting-comparability changes.
-- ---------------------------------------------------------------------------
SELECT
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
    'segment_or_scope_change' AS review_reason
FROM evidence_snippet AS e
JOIN filing AS f ON f.filing_id = e.filing_id
WHERE
    lower(e.snippet) GLOB '*changed its segment structure*'
    OR lower(e.snippet) GLOB '*reportable segment*'
       AND lower(e.snippet) GLOB '*retrospectively adjusted*'
    OR lower(e.snippet) GLOB '*recast*segment*'
    OR lower(e.snippet) GLOB '*change in accounting principle*'
    OR lower(e.snippet) GLOB '*nonreliance*financial*'
ORDER BY f.available_at, f.symbol, e.evidence_id;

-- ---------------------------------------------------------------------------
-- 6. Material 8-K review queue. Item classification is already deterministic;
--    LLM review is for decomposition, scope, actual-versus-estimate, and remedy.
-- ---------------------------------------------------------------------------
SELECT
    f.security_id,
    f.issuer_id,
    f.symbol,
    f.filing_id,
    f.accession,
    f.form,
    f.available_at,
    f.available_at_precision,
    v.event_id,
    v.event_type,
    v.item,
    v.title,
    e.evidence_id,
    e.snippet,
    e.source_sha256
FROM event_ledger AS v
JOIN filing AS f ON f.filing_id = v.filing_id
JOIN evidence_snippet AS e ON e.filing_id = f.filing_id
WHERE
    v.event_type IN (
        'material_agreement',
        'agreement_termination',
        'acquisition_or_disposition',
        'results_of_operations',
        'financial_obligation',
        'exit_or_disposal_costs',
        'material_impairment',
        'auditor_change',
        'nonreliance_on_financials',
        'change_in_control',
        'director_or_officer_change',
        'other_material_event'
    )
    AND (
        lower(e.snippet) GLOB '*charge*'
        OR lower(e.snippet) GLOB '*guidance*'
        OR lower(e.snippet) GLOB '*expected*'
        OR lower(e.snippet) GLOB '*license*'
        OR lower(e.snippet) GLOB '*remed*'
        OR lower(e.snippet) GLOB '*acquisition*'
        OR lower(e.snippet) GLOB '*restructur*'
        OR lower(e.snippet) GLOB '*performance goal*'
    )
ORDER BY f.available_at, f.symbol, v.event_id, e.evidence_id;

-- ---------------------------------------------------------------------------
-- 7. Disclosure-delta candidate pairs. The LLM must compare only evidence that
--    is available at or before the caller-supplied :signal_timestamp.
--    Bind :symbol, :base_form, and :signal_timestamp.
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
-- 8. 13F rows normally bypass LLM. Use this query only for identifier/alias
--    normalization candidates, never for commercial-relation inference.
-- ---------------------------------------------------------------------------
SELECT
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
    h.issuer_name IS NULL
    OR trim(h.issuer_name) = ''
    OR h.cusip IS NULL
    OR trim(h.cusip) = ''
    OR h.issuer_name GLOB '*  *'
ORDER BY f.available_at, f.symbol, h.holding_id;

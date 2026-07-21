-- Select evidence that may describe future or conditional events.
-- This query creates candidates only. It does not prove occurrence or probability.

SELECT
    f.security_id,
    f.issuer_id,
    f.symbol,
    f.filing_id,
    f.accession,
    f.form,
    f.base_form,
    f.available_at,
    f.available_at_precision,
    e.section_id,
    e.evidence_id,
    e.snippet,
    e.source_sha256,
    'potential_future_event' AS candidate_reason,
    CASE
        WHEN lower(e.snippet) GLOB '*subject to*'
          OR lower(e.snippet) GLOB '*depends on*'
          OR lower(e.snippet) GLOB '*conditioned on*'
          OR lower(e.snippet) GLOB '*if *'
            THEN 'conditional_potential_candidate'
        WHEN lower(e.snippet) GLOB '*expect*'
          OR lower(e.snippet) GLOB '*anticipat*'
          OR lower(e.snippet) GLOB '*forecast*'
          OR lower(e.snippet) GLOB '*up to*'
            THEN 'expected_not_occurred_candidate'
        WHEN lower(e.snippet) GLOB '*plan*'
          OR lower(e.snippet) GLOB '*intend*'
          OR lower(e.snippet) GLOB '*scheduled*'
          OR lower(e.snippet) GLOB '*proposed*'
            THEN 'announced_not_occurred_candidate'
        WHEN lower(e.snippet) GLOB '*may*'
          OR lower(e.snippet) GLOB '*might*'
          OR lower(e.snippet) GLOB '*could*'
          OR lower(e.snippet) GLOB '*possible*'
          OR lower(e.snippet) GLOB '*potential*'
            THEN 'hypothetical_or_conditional_candidate'
        ELSE 'undetermined_candidate'
    END AS preliminary_occurrence_hint
FROM evidence_snippet AS e
JOIN filing AS f ON f.filing_id = e.filing_id
WHERE
    f.base_form IN (
        '10-K', '10-Q', '8-K', '20-F', '40-F', '6-K',
        'DEF 14A', 'PRE 14A', 'DEFA14A', 'SD', 'CORRESP',
        'S-1', 'S-3', 'S-4', '424B2', '424B3', '424B4',
        '424B5', '424B7', '424B8', 'FWP'
    )
    AND (
        lower(e.snippet) GLOB '* may *'
        OR lower(e.snippet) GLOB '* might *'
        OR lower(e.snippet) GLOB '* could *'
        OR lower(e.snippet) GLOB '* expect*'
        OR lower(e.snippet) GLOB '* anticipat*'
        OR lower(e.snippet) GLOB '* plan*'
        OR lower(e.snippet) GLOB '* intend*'
        OR lower(e.snippet) GLOB '* target*'
        OR lower(e.snippet) GLOB '* subject to*'
        OR lower(e.snippet) GLOB '* depends on*'
        OR lower(e.snippet) GLOB '* conditioned on*'
        OR lower(e.snippet) GLOB '* up to *'
        OR lower(e.snippet) GLOB '* potential*'
        OR lower(e.snippet) GLOB '* possible*'
        OR lower(e.snippet) GLOB '* proposed*'
        OR lower(e.snippet) GLOB '* scheduled*'
    )
ORDER BY f.available_at, f.symbol, e.evidence_id;

-- Important review rules:
-- 1. Modal language is only a candidate signal.
-- 2. Split occurred facts from future statements in the same snippet.
-- 3. A later filing confirming the event must create a separate occurred record.
-- 4. Never use future outcomes to classify the earlier evidence.
-- 5. Do not turn management targets, guidance, or compensation metrics into actual results.

# LLM Review Output Contract — Trust Semantics

## Write boundary

The LLM must not directly update authoritative tables:

- `filing`, `filing_document`, `filing_section`, `filing_table`;
- `xbrl_fact`, `form13f_holding`, `event_ledger`;
- `evidence_snippet`;
- existing deterministic `semantic_assertion` or `company_relation` rows.

Write append-only JSONL to:

```text
data/sec_yfinance/reviews/<run_id>/<batch_id>/records.jsonl
```

A separate validator or human approval step may promote a review result. The LLM never emits an accepted database status.

## One-record rule

Each line represents one atomic semantic decision for one primary evidence item and one trust profile.

Split records when they differ by:

- attribution or speaker;
- actual versus estimate or interpretation;
- occurred versus potential state;
- counterparty or relation role;
- product generation or lifecycle state;
- period, segment, geography, accounting basis, currency, unit, or scale;
- evidence trust or inference depth.

## Required record

```json
{
  "schema_version": "sec-llm-review-v2",
  "review_id": "stable review identifier",
  "run_id": "review run identifier",
  "batch_id": "review batch identifier",
  "reviewed_assertion_id": null,
  "reviewed_relation_id": null,
  "resolves_prior_review_id": null,
  "candidate_reason": "trust_profile_reconstruction",
  "primary_evidence_id": "evidence identifier",
  "corroborating_evidence_ids": [],
  "conflicting_evidence_ids": [],
  "security_id": "security identifier",
  "issuer_id": "issuer identifier",
  "symbol": "AMD",
  "filing_id": "filing identifier",
  "accession": "0000002488-25-000166",
  "form": "10-Q",
  "signal_timestamp": "2026-01-01T15:00:00Z",
  "source_available_at": "2025-11-04T23:07:50Z",
  "source_available_at_precision": "datetime",
  "action": "create_candidate",
  "claim_class": "risk_hypothesis",
  "occurrence_status": "conditional_potential",
  "subject_key": "security:AMD",
  "predicate": "potential_event",
  "object": {
    "event_type": "future_export_licensed_sales",
    "affected_scope": {
      "product": "AMD Instinct MI308",
      "geography": "China"
    },
    "trigger_conditions": [
      "customer demand exists",
      "applicable import rules permit shipment",
      "required export licenses are available"
    ],
    "expected_window": null,
    "quantitative_range": null,
    "probability_language": "depends on",
    "issuer_commitment_level": "conditional"
  },
  "explicitness": "explicit",
  "trust_profile": {
    "evidence_integrity": "verified",
    "source_authority": "filed_primary_document",
    "statement_attribution": "management_estimate",
    "semantic_directness": "explicit_text",
    "inference_depth": 0,
    "inference_premises": ["evidence identifier"],
    "inference_bridge": null,
    "temporal_eligibility": "eligible_datetime",
    "scope_fidelity": "exact",
    "corroboration_state": "single_information_event",
    "contradiction_state": "none",
    "economic_truth_status": "not_independently_assessed",
    "semantic_support_score": 0.96,
    "trust_tier": "C"
  },
  "confidence": 0.96,
  "status": "review_required",
  "effective_from": null,
  "effective_to": null,
  "delta_class": null,
  "rationale": "The filing explicitly describes future sales as conditional. The evidence strongly supports that semantic representation, but it does not establish that sales occurred or will occur.",
  "limitations": ["future_state_not_observed"],
  "reviewer": {
    "provider": "local",
    "model": "model-name",
    "model_version": "version-or-checkpoint",
    "temperature": 0
  },
  "prompt_hash": "sha256 of system plus task prompt",
  "taxonomy_version": "version identifier",
  "trust_policy_version": "trust-semantics-v1",
  "created_at": "2026-07-21T00:00:00Z"
}
```

## Allowed actions

```text
accept
reject
supersede
create_candidate
no_change
taxonomy_candidate
```

`accept` recommends retaining a deterministic record. It does not authorize `status = accepted`.

## Candidate reasons

```text
trust_profile_reconstruction
attribution_ambiguity
inference_audit
product_lifecycle_state
mixed_actual_estimate_risk
potential_future_event
relation_role_refinement
relation_scope_missing
contradiction_review
disclosure_delta
segment_comparability
legal_remedy_decomposition
taxonomy_candidate
false_positive_correction
```

## Claim classes

```text
reported_fact
management_estimate
risk_hypothesis
policy_or_rule
management_interpretation
third_party_statement
reviewer_inference
```

Claim class describes the financial meaning. `trust_profile.statement_attribution` describes who or what produced the statement.

## Occurrence status

Every output record requires one:

```text
occurred
ongoing
announced_not_occurred
expected_not_occurred
conditional_potential
hypothetical_risk
undetermined
not_applicable
```

Future states require `predicate = potential_event`. Do not use confidence as an event probability.

## Trust-profile enums

### Evidence integrity

```text
verified
verified_with_storage_gap
unknown
failed
```

### Source authority

```text
structured_sec_field
inline_xbrl_or_xml
filed_table
filed_primary_document
filed_exhibit
third_party_text_embedded_in_filing
reviewer_generated
```

### Statement attribution

```text
structured_sec_fact
issuer_reported_statement
management_estimate
management_interpretation
third_party_statement_in_filing
legal_or_regulatory_assertion
reviewer_inference
```

### Semantic directness

```text
exact_structured
explicit_text
normalized_explicit
composed_explicit
inferred
```

### Temporal eligibility

```text
eligible_datetime
eligible_date_only
ineligible_future
unknown
```

### Scope fidelity

```text
exact
bounded
partial
ambiguous
not_comparable
```

### Corroboration state

```text
single_evidence
single_information_event
same_filing_independent_structure
prior_filing_consistent
cross_form_consistent
conflicted
not_applicable
```

### Contradiction state

```text
none
same_time_conflict
later_supersession
scope_conflict
measurement_conflict
unresolved
```

### Economic truth status

```text
structurally_reported
issuer_attested
internally_corroborated
attributed_only
not_independently_assessed
contradicted_by_eligible_evidence
not_applicable
```

### Trust tier

```text
A
B
C
D
X
```

Trust tier is derived from dimensions. It must never be assigned from the numeric score alone.

## Inference contract

`inference_depth` must be an integer from 0 to 3:

```text
0 direct structured or explicit statement
1 controlled normalization
2 composition of explicit premises
3 unstated bridge or reviewer inference
```

Rules:

- `inference_premises` must list every evidence ID used.
- `inference_bridge` is required for depth 2 or 3.
- Depth 3 requires challenger review and cannot be automatically promoted.
- If the bridge is not uniquely defensible, use `no_change`.
- Co-mention, sequence, embedding similarity, and later outcomes are not valid hidden bridges.

## Confidence compatibility rule

`confidence` is retained for compatibility only.

It must satisfy:

```text
confidence == trust_profile.semantic_support_score
```

It measures support for the exact semantic representation. It does not measure:

- truthfulness of management;
- likelihood of a future event;
- investment conviction;
- materiality;
- expected return;
- source prestige.

## Corroboration rules

Do not count these as independent corroboration:

- duplicated wording;
- multiple snippets from one sentence;
- a deterministic assertion plus its own evidence;
- an 8-K and its attached issuer press release as separate independent sources;
- the same press release copied into several exhibits.

When evidence is not independent, use `single_information_event`.

## Economic truth rules

- SEC filing status proves filing provenance and timing, not the objective truth of every statement.
- A filed forecast remains `not_independently_assessed`.
- A management causal explanation remains `management_interpretation` unless another governed layer verifies it.
- A legal allegation is `attributed_only` until an eligible decision or order establishes a procedural outcome.
- A structured reported value may be `structurally_reported`; do not rename it `proven_true`.
- Later confirmation creates a new record and never retrospectively upgrades the earlier record.

## Identity and evidence rules

- Identity fields must match the primary evidence row.
- Anonymous entities stay anonymous.
- A counterparty mentioned in one issuer's filing does not become an issuer-side fact for that counterparty.
- `primary_evidence_id` is mandatory.
- Corroborating/conflicting evidence must be supplied and PIT-eligible.
- `source_available_at` must exactly match the database.
- No current web or external evidence may be added in this review batch.

## Timing rules

- `source_available_at <= signal_timestamp` is mandatory.
- Date-only evidence is invalid for intraday review.
- `effective_from` never changes when evidence became knowable.
- Later outcomes cannot influence earlier semantic classification or trust tier.
- PIT/integrity failure requires `trust_tier = X`.

## Action rules

- `accept`: requires a reviewed assertion or relation ID.
- `reject`: requires a reviewed record ID and concrete reason.
- `supersede`: requires a reviewed record ID and corrected atomic claim.
- `create_candidate`: requires supported predicate/object.
- `no_change`: rationale must explain insufficient evidence or non-unique inference.
- `taxonomy_candidate`: object must include canonical label, definition, parent, aliases, and collision notes.

## Limitations

Suggested labels:

```text
management_claim_unverified
third_party_claim_only
legal_allegation_only
future_state_not_observed
scope_ambiguous
relation_direction_uncertain
non_independent_corroboration
inference_bridge_required
period_not_comparable
unit_or_scale_uncertain
issuer_side_evidence_missing
eligible_conflict_unresolved
```

## Batch manifest

```json
{
  "schema_version": "sec-llm-review-batch-v2",
  "run_id": "...",
  "batch_id": "...",
  "signal_timestamp": "...",
  "candidate_query_hash": "...",
  "candidate_reason_counts": {},
  "occurrence_status_counts": {},
  "trust_tier_counts": {},
  "attribution_counts": {},
  "inference_depth_counts": {},
  "economic_truth_status_counts": {},
  "input_assertion_count": 100,
  "input_relation_count": 10,
  "input_evidence_count": 100,
  "output_record_count": 100,
  "action_counts": {},
  "model": {},
  "prompt_hash": "...",
  "taxonomy_version": "...",
  "trust_policy_version": "trust-semantics-v1",
  "source_database_sha256": "...",
  "started_at": "...",
  "completed_at": "...",
  "errors": []
}
```

## Validation gate

Reject the batch when any of these is non-zero:

```text
missing_primary_evidence
unknown_evidence_id
identity_mismatch
source_time_mismatch
evidence_after_signal_timestamp
intraday_date_precision_use
missing_trust_profile
invalid_trust_enum
confidence_score_mismatch
trust_tier_derived_from_score_only
pit_or_integrity_failure_not_tier_x
missing_inference_premise
missing_inference_bridge
hidden_inference_bridge
duplicate_evidence_counted_as_independent
sec_filing_treated_as_proof_of_economic_truth
management_estimate_stored_as_verified_fact
legal_allegation_stored_as_proven_fact
unsupported_economic_truth_upgrade
later_outcome_used_to_regrade_history
accepted_status_emitted
multi_claim_record
external_enrichment_used
source_evidence_mutation
```

Semantic uncertainty may return `no_change`; governance violations fail the batch.

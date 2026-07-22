# LLM Review Output Contract — Trust and Promotion Routing

## Write boundary

The LLM must not directly update authoritative tables:

- `filing`, `filing_document`, `filing_section`, `filing_table`;
- `xbrl_fact`, `form13f_holding`, `event_ledger`;
- `evidence_snippet`;
- deterministic `semantic_assertion` or `company_relation` rows.

Write append-only JSONL to:

```text
data/sec_yfinance/reviews/<run_id>/<batch_id>/records.jsonl
```

A validator or human approval step may promote a reviewed result. The LLM never writes `status = accepted` and never mints promotion level A.

## Request-unit versus output-unit

One LLM request corresponds to one `evidence_group_id`, normally one governed evidence sentence/snippet with all candidate rows produced from it.

One request may return multiple decisions, but each JSONL line remains one atomic subject-predicate-object claim.

Do not call the LLM separately for every company mention or topic candidate generated from the same evidence.

## Required record

```json
{
  "schema_version": "sec-llm-review-v3",
  "review_id": "stable review identifier",
  "run_id": "review run identifier",
  "batch_id": "review batch identifier",

  "input_promotion_level": "C",
  "llm_route": "mandatory",
  "evidence_group_id": "stable evidence-group identifier",
  "candidate_ids": ["candidate-1", "candidate-2"],
  "promotion_recommendation": "promote_candidate_to_B",
  "routing_context": {
    "promotion_policy_version": "promotion-routing-v1",
    "section_role": "issuer_risk",
    "grouping_key": "issuer|filing|section|sentence-hash",
    "dedupe_cluster_id": null,
    "rule_id": "relation-rule-id",
    "rule_version": "rule-version",
    "sample_rate": null,
    "sample_seed": null,
    "sample_reason": null,
    "population_count": null
  },

  "reviewed_assertion_id": null,
  "reviewed_relation_id": null,
  "resolves_prior_review_id": null,
  "candidate_reason": "relation_role_refinement",
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
  "claim_class": "reported_fact",
  "occurrence_status": "ongoing",
  "subject_key": "security:AMD",
  "predicate": "foundry_dependency_on",
  "object": {
    "target_entity_key": "company:TSMC",
    "product_scope": "explicitly supported scope only"
  },
  "explicitness": "explicit",

  "trust_profile": {
    "evidence_integrity": "verified",
    "source_authority": "filed_primary_document",
    "statement_attribution": "issuer_reported_statement",
    "semantic_directness": "normalized_explicit",
    "inference_depth": 1,
    "inference_premises": ["evidence identifier"],
    "inference_bridge": null,
    "temporal_eligibility": "eligible_datetime",
    "scope_fidelity": "bounded",
    "corroboration_state": "single_information_event",
    "contradiction_state": "none",
    "economic_truth_status": "issuer_attested",
    "semantic_support_score": 0.95,
    "trust_tier": "B"
  },

  "confidence": 0.95,
  "status": "review_required",
  "effective_from": null,
  "effective_to": null,
  "delta_class": null,
  "rationale": "The issuer explicitly describes the named manufacturing dependency; scope is limited to the products stated in the evidence.",
  "limitations": ["issuer_side_evidence_only"],
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

## Promotion and route fields

### Input promotion level

```text
A
B
C
D1
D2
D3
R
```

Normal routing:

| Level | Formal library | Normal LLM route |
|---|---:|---|
| A | yes | none |
| B | yes | sampled audit |
| C | no | mandatory by evidence group |
| D1 | no | grouped mandatory |
| D2 | no | aggregate/deduplicate/prioritize |
| D3 | no | no default review |
| R | no | rejection-rule audit sample |

### LLM route

```text
none
sampled_audit
mandatory
grouped_mandatory
aggregate_then_review
no_default_review
rejection_audit
```

A/D3 records should normally produce no review output. Their presence requires an explicit QA or targeted-review reason in `routing_context.sample_reason`.

### Promotion recommendation

```text
keep_formal_B
promote_candidate_to_B
retain_C_or_D_review
reject_to_R
rule_regression_candidate
no_change
```

The LLM cannot recommend or create A. A requires deterministic structured/direct validation.

A B audit normally returns `keep_formal_B` or `no_change`. A B change requires concrete evidence and challenger review.

An R audit failure returns `rule_regression_candidate`; it does not directly promote the rejected record.

## Routing context

Every record requires:

```text
promotion_policy_version
grouping_key
section_role
rule_id
rule_version
```

Nullable sampling/dedup fields must still be present:

```text
dedupe_cluster_id
sample_rate
sample_seed
sample_reason
population_count
```

For B and R audits, sampling metadata is mandatory and must be replayable.

For D2, `dedupe_cluster_id` is mandatory.

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
rule_audit
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

Claim class describes financial meaning. `statement_attribution` describes who or what produced the statement.

## Occurrence status

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

Future states require `predicate = potential_event`. Confidence is never event probability.

## Trust profile

The required trust dimensions and enums are defined in `TRUST_SEMANTICS_POLICY.md`.

Important invariants:

- `confidence == trust_profile.semantic_support_score`;
- trust tier is derived from all dimensions, not score alone;
- PIT/integrity failure requires Tier X;
- SEC filing status proves provenance/timing, not objective truth of every statement;
- management estimates and interpretations may have high semantic support while economic truth remains unassessed;
- repeated wording and several candidates from one sentence are not independent corroboration.

## Evidence grouping rules

`evidence_group_id` must be stable and reproducible from governed identifiers, normally:

```text
issuer_id
+ filing_id/accession
+ section_id or section_role
+ normalized evidence sentence hash
```

`candidate_ids` must contain every candidate reviewed in the request. Each atomic output may reference the relevant subset but must preserve the request-level group.

D1/D2 review is invalid if the same evidence was sent once per candidate row.

For D2 aggregation, preserve all evidence IDs and PIT times even when repeated sentences are clustered.

## Sampling rules

B and R sampling must record:

- rule ID/version;
- promotion policy version;
- deterministic sample seed/hash rule;
- configured sample rate;
- population and sample counts;
- strata and sample reason.

Recommended policy ranges:

```text
B normal audit 1%-5%, higher for configured high-impact relations
R rule audit 0.1%-1%
```

Do not treat ranges as hardcoded constants. Store the actual run configuration.

## Inference contract

```text
0 direct structured or explicit statement
1 controlled normalization
2 composition of explicit premises
3 unstated bridge or reviewer inference
```

- list every premise evidence ID;
- require `inference_bridge` for depth 2/3;
- depth 3 requires challenger review and cannot be automatically promoted;
- co-mention, sequence, embedding similarity, later outcomes, and same-industry presence are not valid hidden bridges.

## Economic truth and corroboration

- A filed forecast is trustworthy evidence of the forecast, not proof of realization.
- A legal allegation remains attributed unless eligible procedural evidence establishes an outcome.
- An 8-K and its issuer press release are normally one information event.
- A deterministic candidate plus its source evidence is not corroboration.
- Later actual results create new records; they do not upgrade an earlier historical estimate.

## Action rules

- `accept`: requires a reviewed deterministic ID and does not emit accepted status.
- `reject`: requires a reviewed ID and concrete reason.
- `supersede`: requires corrected atomic semantics and challenger review when a formal B record changes.
- `create_candidate`: requires supported predicate/object.
- `no_change`: explains insufficient evidence or confirms sampled B/R audit.
- `taxonomy_candidate`: includes canonical label, definition, parent, aliases, evidence, and collision notes.

## Batch manifest

```json
{
  "schema_version": "sec-llm-review-batch-v3",
  "run_id": "...",
  "batch_id": "...",
  "signal_timestamp": "...",
  "candidate_query_hash": "...",
  "promotion_policy_version": "promotion-routing-v1",
  "promotion_level_population_counts": {},
  "promotion_level_selected_counts": {},
  "llm_route_counts": {},
  "evidence_group_count": 0,
  "candidate_row_count": 0,
  "deduplicated_candidate_count": 0,
  "sample_configuration": {
    "sample_seed": "...",
    "B_sample_rate": null,
    "R_sample_rate": null,
    "strata": []
  },
  "candidate_reason_counts": {},
  "occurrence_status_counts": {},
  "trust_tier_counts": {},
  "attribution_counts": {},
  "inference_depth_counts": {},
  "economic_truth_status_counts": {},
  "promotion_recommendation_counts": {},
  "output_record_count": 0,
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

Reject the batch when any is non-zero:

```text
all_non_A_sent_to_llm
A_sent_without_explicit_qa
B_population_sent_without_sampling
B_sampling_not_replayable
C_eligible_evidence_group_skipped
D_candidate_row_used_as_request_unit
D1_not_grouped
D2_not_deduplicated
D3_sent_by_default
R_used_as_normal_review_queue
R_sampling_not_replayable
promotion_level_confused_with_trust_tier
llm_directly_mints_A
missing_evidence_group_id
candidate_group_membership_mismatch
missing_primary_evidence
unknown_evidence_id
identity_mismatch
source_time_mismatch
evidence_after_signal_timestamp
intraday_date_precision_use
missing_trust_profile
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

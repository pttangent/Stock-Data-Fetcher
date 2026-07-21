# LLM Review Output Contract

## Write boundary

The LLM must not directly update authoritative tables:

- `filing`, `filing_document`, `filing_section`, `filing_table`;
- `xbrl_fact`, `form13f_holding`, `event_ledger`;
- `evidence_snippet`;
- existing deterministic `semantic_assertion` or `company_relation` rows.

The reviewer writes append-only JSONL to:

```text
data/sec_yfinance/reviews/<run_id>/<batch_id>.jsonl
```

A separate validator or human approval step may promote an approved record. The LLM never writes an accepted fact directly.

## One-record rule

Each line represents one atomic decision for one primary evidence item and, where applicable, one reviewed assertion or relation.

Split records when they differ by:

- occurred versus future/potential state;
- actual versus estimate/guidance;
- counterparty or relation role;
- product generation or lifecycle state;
- period, segment, geography, accounting basis, or unit.

## Required record

```json
{
  "schema_version": "sec-llm-review-v1",
  "review_id": "stable review identifier",
  "run_id": "pipeline or review run identifier",
  "batch_id": "review batch identifier",
  "reviewed_assertion_id": null,
  "reviewed_relation_id": null,
  "resolves_prior_review_id": null,
  "candidate_reason": "potential_future_event",
  "primary_evidence_id": "evidence identifier",
  "corroborating_evidence_ids": [],
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
      "Chinese import rules permit shipment",
      "required export licenses are available"
    ],
    "expected_window": null,
    "quantitative_range": null,
    "probability_language": "depends on",
    "issuer_commitment_level": "conditional"
  },
  "explicitness": "explicit",
  "confidence": 0.94,
  "status": "review_required",
  "effective_from": null,
  "effective_to": null,
  "delta_class": null,
  "rationale": "The filing describes future sales as conditional on demand, import rules, and licenses; it does not report that those sales occurred.",
  "limitations": ["future_state_not_observed"],
  "reviewer": {
    "provider": "local",
    "model": "model-name",
    "model_version": "version-or-checkpoint",
    "temperature": 0
  },
  "prompt_hash": "sha256 of system plus task prompt",
  "taxonomy_version": "version identifier",
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

Interpretation:

- `occurred`: the event or accounting impact explicitly happened;
- `ongoing`: a rule, restriction, obligation, process, or state is currently in force;
- `announced_not_occurred`: committed or announced, but not yet completed;
- `expected_not_occurred`: management expects it, but it has not happened;
- `conditional_potential`: may happen only if stated conditions are met;
- `hypothetical_risk`: generic risk possibility without a specific expected event;
- `undetermined`: evidence cannot safely establish occurrence;
- `not_applicable`: non-event semantics such as stable taxonomy or supplier role.

For future/potential states, `predicate` must be:

```text
potential_event
```

The object should preserve, when available:

```text
event_type
affected_scope
trigger_conditions
expected_window
quantitative_range
probability_language
issuer_commitment_level
```

Do not invent missing probability, time, amount, or trigger.

## Potential-to-occurred resolution

A later filing may resolve an earlier potential event. The later record may set:

```text
resolves_prior_review_id = <earlier potential review ID>
```

Rules:

1. Preserve the earlier potential record and its original availability time.
2. Create a new `occurred` or resolution record using later evidence.
3. Never rewrite the earlier record as though the event was already known to have occurred.
4. A cancelled or withdrawn plan is a new resolution event, not deletion.

## Candidate reasons

```text
product_lifecycle_state
mixed_actual_estimate_risk
potential_future_event
relation_role_refinement
relation_scope_missing
disclosure_delta
segment_comparability
legal_remedy_decomposition
taxonomy_candidate
false_positive_correction
```

## Explicitness

Use project database values only:

```text
explicit
estimated
inferred
```

Statement attribution is represented by `claim_class`, not a separate explicitness enum.

## Identity and evidence rules

- Identity fields must match the primary evidence row.
- Anonymous entities stay anonymous.
- A counterparty mentioned in one issuer's filing does not become an issuer-side fact for that counterparty.
- `primary_evidence_id` is mandatory.
- Corroborating evidence must be supplied and PIT-eligible.
- `source_available_at` must exactly match the database.
- Do not paste altered evidence into the output.
- No current web or external evidence may be added in this review batch.

## Timing rules

- `source_available_at <= signal_timestamp` is mandatory.
- Date-precision evidence is invalid for intraday review.
- `effective_from` never changes when the evidence became knowable.
- `created_at` is review time, not source availability.
- Later outcomes cannot influence the earlier semantic classification.

## Action rules

- `accept`: requires a reviewed assertion or relation ID.
- `reject`: requires a reviewed record ID and concrete reason.
- `supersede`: requires a reviewed record ID and corrected atomic claim.
- `create_candidate`: requires supported predicate/object.
- `no_change`: rationale must explain insufficient evidence.
- `taxonomy_candidate`: object must include canonical label, definition, parent, aliases, and collision notes.

## Confidence

Confidence measures evidence-to-semantics support, not whether a potential event will occur.

- New inferred claims below `0.50` are prohibited; use `no_change`.
- Results below `0.90` require challenger review.
- Do not use confidence as an event probability.

## Limitations

Suggested labels:

```text
anonymous_counterparty
management_claim_unverified
scope_ambiguous
period_not_comparable
relation_direction_uncertain
unit_or_scale_uncertain
issuer_side_evidence_missing
future_state_not_observed
condition_incomplete
event_time_not_stated
```

## Batch manifest

```json
{
  "schema_version": "sec-llm-review-batch-v1",
  "run_id": "...",
  "batch_id": "...",
  "signal_timestamp": "...",
  "candidate_query_hash": "...",
  "candidate_reason_counts": {},
  "occurrence_status_counts": {},
  "input_assertion_count": 100,
  "input_relation_count": 10,
  "input_evidence_count": 100,
  "output_record_count": 100,
  "action_counts": {},
  "model": {},
  "prompt_hash": "...",
  "taxonomy_version": "...",
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
invalid_enum
accepted_status_emitted
missing_candidate_reason
missing_occurrence_status
potential_stored_as_occurred
occurred_stored_as_potential
later_resolution_rewrites_prior_state
future_amount_stored_as_actual
condition_missing_for_conditional_event
invented_probability
invented_event_date
missing_model_identity
missing_prompt_hash
multi_claim_record
future_outcome_reference
external_enrichment_used
source_evidence_mutation
```

Semantic uncertainty may return `no_change`; governance violations fail the batch.

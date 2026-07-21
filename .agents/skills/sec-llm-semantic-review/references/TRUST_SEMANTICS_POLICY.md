# Trust Semantics Policy

## Objective

Represent trust as a set of auditable dimensions rather than a single confidence score.

This policy separates:

1. authenticity and integrity of the evidence;
2. authority and attribution of the source statement;
3. support for the proposed semantic mapping;
4. inference used by the reviewer;
5. point-in-time eligibility;
6. scope and comparability;
7. corroboration and contradiction;
8. whether the underlying economic claim is independently established.

A record can be highly trustworthy as a faithful representation of what management said while remaining unverified as an economic fact.

## Mandatory trust profile

Every review record must include:

```json
{
  "evidence_integrity": "verified",
  "source_authority": "filed_primary_document",
  "statement_attribution": "management_estimate",
  "semantic_directness": "explicit_text",
  "inference_depth": 0,
  "inference_premises": ["primary_evidence_id"],
  "inference_bridge": null,
  "temporal_eligibility": "eligible_datetime",
  "scope_fidelity": "exact",
  "corroboration_state": "single_information_event",
  "contradiction_state": "none",
  "economic_truth_status": "not_independently_assessed",
  "semantic_support_score": 0.97,
  "trust_tier": "C"
}
```

## 1. Evidence integrity

Allowed values:

```text
verified
verified_with_storage_gap
unknown
failed
```

### `verified`

Require all applicable checks:

- filing/accession identity matches the database;
- evidence row exists;
- source SHA-256 matches;
- offsets or section identity are reproducible;
- source availability is present;
- no evidence mutation occurred.

### `verified_with_storage_gap`

Use only when the governed record and hash exist but an optional local materialization is unavailable. This does not authorize re-creating evidence from memory.

### `unknown` or `failed`

The claim cannot be used for research. Set `trust_tier = X` and return `no_change` or reject the batch.

## 2. Source authority

Allowed values:

```text
structured_sec_field
inline_xbrl_or_xml
filed_table
filed_primary_document
filed_exhibit
third_party_text_embedded_in_filing
reviewer_generated
```

Source authority describes the record type, not the truth of the underlying claim.

Examples:

- SEC acceptance time is authoritative as a structured SEC field.
- An Inline XBRL revenue value is authoritative as the value filed for that concept/context.
- An earnings-release forecast filed as an exhibit is authoritative evidence of the forecast, not proof the forecast will occur.
- A quoted customer or regulator statement remains attributed third-party text even though it appears in a filing.

## 3. Statement attribution

Allowed values:

```text
structured_sec_fact
issuer_reported_statement
management_estimate
management_interpretation
third_party_statement_in_filing
legal_or_regulatory_assertion
reviewer_inference
```

Rules:

- `issuer_reported_statement` means the issuer states that an actual condition or event existed.
- `management_estimate` covers guidance, targets, expected charges, planned capex, and forecasts.
- `management_interpretation` covers strategy, causal explanations, demand narratives, and management-assigned reasons.
- `third_party_statement_in_filing` remains attributed to the third party.
- `legal_or_regulatory_assertion` records an allegation, order, requirement, decision, or remedy with its procedural status.
- `reviewer_inference` is never disguised as issuer language.

## 4. Semantic directness

Allowed values:

```text
exact_structured
explicit_text
normalized_explicit
composed_explicit
inferred
```

### `exact_structured`

Direct mapping from a structured field, XBRL fact, XML row, or table cell with preserved context.

### `explicit_text`

The subject, predicate, object, scope, and state are directly stated in one evidence window.

### `normalized_explicit`

Only controlled normalization was required, such as:

- `TSMC` to the canonical company identity;
- `began volume production` to a lifecycle predicate;
- unit-preserving number normalization.

### `composed_explicit`

Two or more explicit clauses or eligible evidence rows were combined. Premises and the bridge rule must be recorded.

### `inferred`

The semantic result requires a proposition not explicitly stated. It must remain `review_required`; use `no_change` when another reasonable interpretation exists.

## 5. Inference depth

```text
0 = direct structured or explicit statement
1 = controlled normalization only
2 = composition of explicit premises
3 = unstated bridge or reviewer inference
```

Mandatory rules:

- Record every premise by evidence ID.
- Record the bridge rule in plain language.
- Do not use embeddings, co-mention, temporal sequence, or later outcomes as an unstated bridge.
- Depth 2 requires challenger review when economically material.
- Depth 3 cannot be automatically promoted.
- More evidence does not reduce inference depth unless it explicitly supplies the missing bridge.

## 6. Temporal eligibility

Allowed values:

```text
eligible_datetime
eligible_date_only
ineligible_future
unknown
```

Rules:

- `source_available_at <= signal_timestamp` is mandatory.
- Date-only evidence is not intraday eligible.
- Economic effective time does not replace information availability time.
- Later filings may resolve an earlier event but cannot strengthen the historical trust profile at an earlier timestamp.
- Current observations, later prices, and realized outcomes are forbidden in an earlier PIT review.

Any `ineligible_future` or `unknown` record is Tier X for the requested signal time.

## 7. Scope fidelity

Allowed values:

```text
exact
bounded
partial
ambiguous
not_comparable
```

Check separately:

- issuer versus counterparty;
- consolidated versus segment;
- direct customer versus distributor/end customer;
- product family versus SKU/generation;
- wafer fabrication versus packaging/assembly/test;
- actual period versus guidance period;
- GAAP versus non-GAAP;
- currency, unit, scale, geography, and legal jurisdiction.

A claim may be explicit but still have `scope_fidelity = partial` when the evidence supports the relationship but not the proposed product scope.

## 8. Corroboration state

Allowed values:

```text
single_evidence
single_information_event
same_filing_independent_structure
prior_filing_consistent
cross_form_consistent
conflicted
not_applicable
```

### Independence rules

Do not count these as independent corroboration:

- repeated wording in the same section;
- duplicated risk language;
- the same press release reproduced in multiple exhibits;
- an 8-K and its attached press release when both originate from the same issuer information event;
- a deterministic assertion and the evidence from which it was extracted;
- several snippets cut from one sentence.

Possible internal corroboration includes:

- narrative plus a genuinely separate filed table/XBRL fact;
- distinct filing sections that independently state the same scoped fact;
- comparable earlier filings, while preserving each filing's PIT state.

Corroboration increases support for representation only. It does not transform management interpretation into objective truth.

## 9. Contradiction state

Allowed values:

```text
none
same_time_conflict
later_supersession
scope_conflict
measurement_conflict
unresolved
```

Rules:

- Preserve conflicting assertions separately.
- A later actual result may supersede an earlier estimate economically but does not make the earlier estimate an error.
- A changed product scope is not necessarily a contradiction.
- Different GAAP/non-GAAP or segment scopes are `scope_conflict` or `not_comparable`, not automatic factual conflicts.
- Do not choose the statement that later matched market outcomes.

## 10. Economic truth status

Allowed values:

```text
structurally_reported
issuer_attested
internally_corroborated
attributed_only
not_independently_assessed
contradicted_by_eligible_evidence
not_applicable
```

Interpretation:

- `structurally_reported`: the value/state is a structured filed record. This still means “reported as filed.”
- `issuer_attested`: the issuer explicitly states the fact.
- `internally_corroborated`: separate eligible project evidence supports the same scoped assertion.
- `attributed_only`: the filing reports another party's statement, allegation, or position.
- `not_independently_assessed`: forecast, interpretation, strategy, potential event, or claim not independently established by this project.
- `contradicted_by_eligible_evidence`: supplied PIT-eligible evidence directly conflicts.
- `not_applicable`: taxonomy or purely procedural records where economic truth is not the question.

Never use `verified_true`, `proven`, or similar labels unless the project defines a separate external verification pipeline.

## 11. Semantic support score

`semantic_support_score` measures only how strongly the supplied eligible evidence supports the exact semantic representation.

It is not:

- probability that an event will happen;
- probability management is truthful;
- investment conviction;
- source prestige;
- materiality;
- expected return;
- correctness judged using future outcomes.

Guidance:

```text
0.98-1.00 exact structured mapping with complete scope
0.90-0.97 explicit statement or controlled normalization
0.75-0.89 bounded composition with explicit premises
0.50-0.74 material inference or unresolved scope
below 0.50 return no_change
```

The compatibility field `confidence` must equal this score exactly.

## 12. Trust tier

Allowed values:

```text
A
B
C
D
X
```

### Tier A

- evidence integrity verified;
- PIT eligible;
- exact structured/direct mapping;
- scope exact or bounded;
- no material contradiction.

### Tier B

- evidence integrity verified;
- explicit issuer or official statement;
- semantic mapping strong;
- underlying economic truth may remain issuer-attested rather than independently verified.

### Tier C

- management estimate or interpretation;
- attributed/legal statement;
- potential event;
- bounded multi-clause composition;
- economically useful but not an established realized fact.

### Tier D

- inference depth 3;
- ambiguous scope or direction;
- material unresolved contradiction;
- candidate only.

### Tier X

- integrity failure;
- PIT failure;
- missing evidence identity;
- source-time mismatch;
- unusable for the requested research timestamp.

Trust tier must be derived from dimensions, never assigned from score alone.

## Project examples

### MU HBM4 sampling

```text
Evidence supports: samples delivered.
Attribution: issuer_reported_statement.
Semantic directness: explicit_text.
Occurrence: occurred for sampling.
Economic truth: issuer_attested.
Trust tier: B.
```

It does not support volume production. A reviewer inference that sampling implies production is prohibited.

### AMD MI308 charge

A filed table/XBRL amount can be Tier A as the amount reported for the filed period. The statement that the charge reflects future lost revenue would require a different assertion and likely be unsupported.

### AMD future China sales

The filing can strongly support that management described sales as conditional on demand, rules, and licenses. That potential-event representation may have semantic support above 0.90, while economic truth remains `not_independently_assessed` and trust tier remains C.

### NVIDIA H20 estimate and actual

The earlier estimate and later actual charge are both trustworthy representations of their respective filings. The later actual does not retrospectively upgrade the earlier estimate from Tier C to Tier A/B.

### AVGO AI Revenue PSU

The compensation framework may be an occurred Tier A/B governance fact. Future target achievement is a Tier C conditional potential event. It is not realized revenue or ordinary guidance.

### GOOGL antitrust matter

A court decision or filed order may be Tier A/B for the procedural event. Allegations remain `attributed_only`; future financial effect remains potential unless explicitly realized.

## Hard failures

Reject a batch for:

```text
missing_trust_profile
confidence_score_mismatch
trust_tier_derived_from_score_only
sec_filing_treated_as_proof_of_economic_truth
management_estimate_stored_as_verified_fact
legal_allegation_stored_as_proven_fact
duplicate_evidence_counted_as_independent
hidden_inference_bridge
unsupported_economic_truth_upgrade
later_outcome_used_to_regrade_history
pit_or_integrity_failure_not_tier_x
```

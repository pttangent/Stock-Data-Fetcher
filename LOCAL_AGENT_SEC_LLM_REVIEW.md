# Local Agent Instruction — SEC Trust-Semantic Review

## Working boundary

Work only in:

```text
D:\DEV\AnotherNetworkFactory\SEC_Yfinance_Fetcher
```

Use branch:

```text
agent/sec-llm-semantic-review-potential
```

This branch is based on:

```text
300026e8e2571e4b03dabf9dd172d4b65b7fab74
Raise batch filing cap from 100 to 200
```

Do not edit the source metadata parquet, raw SEC evidence, filing identity, XBRL facts, tables, evidence snippets, hashes, timestamps, or existing accepted assertions.

The LLM stage is not a second parser, a filing summarizer, or an investment analyst. It reviews only selected semantic residue and reconstructs the **meaning of trust** for each claim.

## Mandatory Skill files

Read in this order:

```text
.agents/skills/sec-llm-semantic-review/SKILL.md
.agents/skills/sec-llm-semantic-review/references/PIT_POLICY.md
.agents/skills/sec-llm-semantic-review/references/TRUST_SEMANTICS_POLICY.md
.agents/skills/sec-llm-semantic-review/references/FINANCIAL_SEMANTIC_POLICY.md
.agents/skills/sec-llm-semantic-review/references/POTENTIAL_EVENT_POLICY.md
.agents/skills/sec-llm-semantic-review/references/REVIEW_OUTPUT_CONTRACT.md
.agents/skills/sec-llm-semantic-review/references/UPLOADED_ARCHIVE_CASEBOOK.md
.agents/skills/sec-llm-semantic-review/assets/review_batch_prompt.md
.agents/skills/sec-llm-semantic-review/assets/llm_review_record.schema.json
```

Candidate queries:

```text
.agents/skills/sec-llm-semantic-review/assets/select_trust_review_candidates.sql
.agents/skills/sec-llm-semantic-review/assets/select_review_candidates.sql
.agents/skills/sec-llm-semantic-review/assets/select_potential_event_candidates.sql
```

## Core trust principle

Never answer “Is this trustworthy?” with one number.

For each selected claim, distinguish:

```text
1. Evidence trust
   Is the source authentic, hash-verified, traceable, and PIT-eligible?

2. Semantic trust
   Does the source support this exact subject-predicate-object representation?

3. Economic truth
   Does this project independently know the underlying economic statement is true?
```

Examples:

```text
A filed forecast can be:
- evidence_integrity = verified
- semantic_support_score = 0.97
- economic_truth_status = not_independently_assessed
- trust_tier = C
```

This means we are highly confident that management made the forecast and that the semantic extraction is faithful. It does not mean the forecast has a 97% chance of occurring.

## Mandatory trust profile

Every JSONL record must include:

```text
evidence_integrity
source_authority
statement_attribution
semantic_directness
inference_depth
inference_premises
inference_bridge
temporal_eligibility
scope_fidelity
corroboration_state
contradiction_state
economic_truth_status
semantic_support_score
trust_tier
```

Compatibility rule:

```text
confidence == trust_profile.semantic_support_score
```

`confidence` is not truth probability, event probability, investment conviction, materiality, or expected return.

## SEC authority boundary

SEC provenance is authoritative for:

- filing identity;
- issuer/CIK as filed;
- accession and form;
- acceptance/public availability time;
- submitted structured fields and attached documents;
- what the issuer or attributed party stated.

SEC filing status does not automatically prove:

- management estimates will occur;
- management causal explanations are objectively correct;
- legal allegations are true;
- risk disclosures are realized;
- a product mention means shipment or revenue;
- a 13F holding implies partnership, control, or endorsement;
- a named company has the exact commercial role inferred by the reviewer.

## Review workflow

### 1. Preflight

```powershell
cd D:\DEV\AnotherNetworkFactory\SEC_Yfinance_Fetcher
git fetch origin
git checkout agent/sec-llm-semantic-review-potential
git pull --ff-only
pytest
python -m compileall -q .\src
esl-sec --config .\config\sec_pipeline.local.json validate `
  --output .\reports\pre-llm-validation.json
```

Do not begin LLM review unless deterministic validation passes.

### 2. Freeze the batch

Set:

```text
signal_timestamp
run_id
batch_id
candidate_reason
candidate SQL text
candidate SQL SHA-256
source database SHA-256
model/version/temperature
prompt SHA-256
taxonomy version
trust policy version = trust-semantics-v1
```

Use only evidence with:

```text
source_available_at <= signal_timestamp
```

Date-only evidence is not eligible for intraday signals.

### 3. Select a narrow queue

Start with:

```text
select_trust_review_candidates.sql
```

Do not send the whole database to the LLM. Review only records selected because of:

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

### 4. Reconstruct attribution

Choose exactly one:

```text
structured_sec_fact
issuer_reported_statement
management_estimate
management_interpretation
third_party_statement_in_filing
legal_or_regulatory_assertion
reviewer_inference
```

Do not convert attributed or alleged content into issuer-observed fact.

### 5. Audit inference

Use:

```text
inference_depth = 0 direct structured/explicit
inference_depth = 1 controlled normalization
inference_depth = 2 composition of explicit premises
inference_depth = 3 unstated bridge/reviewer inference
```

For depth 2 or 3:

- list every premise evidence ID;
- write the bridge rule explicitly;
- require challenger review;
- use `no_change` if another reasonable bridge exists.

Prohibited hidden bridges:

- co-mention;
- same industry;
- temporal sequence;
- embedding similarity;
- later stock-price reaction;
- later filing outcome;
- outside knowledge not present in the governed batch.

### 6. Assess corroboration correctly

These are not independent corroboration:

- repeated wording in one filing;
- multiple snippets from one sentence;
- one deterministic assertion and its source evidence;
- an 8-K and its attached issuer press release;
- the same release copied into several exhibits.

Use `single_information_event` for these cases.

### 7. Separate occurred and potential

Every event-like record requires one:

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

Future states use:

```text
predicate = potential_event
```

A later actual event is a new record linked through `resolves_prior_review_id`. Never rewrite the earlier potential state.

### 8. Assess economic truth conservatively

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

Do not emit `proven_true`, `verified_true`, or equivalent labels.

### 9. Derive trust tier

```text
A = structurally verified and semantically direct
B = explicit issuer/official assertion; economic truth may remain issuer-attested
C = estimate, interpretation, attributed/legal statement, potential event, bounded composition
D = reviewer inference, ambiguous scope/direction, unresolved material conflict
X = evidence-integrity or PIT failure; unusable
```

A high semantic score does not force Tier A or B.

### 10. Write append-only output

Directory:

```text
data/sec_yfinance/reviews/<RUN_ID>/<BATCH_ID>/
```

Required files:

```text
records.jsonl
manifest.json
candidate_query.sql
candidate_query.sha256
validation.json
challenger_records.jsonl   # when required
```

Every record must conform to:

```text
.agents/skills/sec-llm-semantic-review/assets/llm_review_record.schema.json
```

All new or corrected records remain:

```text
status = review_required
```

## First controlled trust-review sequence

### Batch 1 — MU lifecycle trust

Review:

```text
HBM4 samples delivered
HBM4 volume production implication
HBM3E production/ramp statements
```

Expected reasoning:

```text
Sample delivery may be Tier B issuer-attested occurred sampling.
It does not support volume production.
Repeated product mentions are not corroboration.
```

### Batch 2 — AMD MI308 trust decomposition

Separate:

```text
recorded charge amount
management explanation of the charge
export-license rule
licenses reportedly granted
future China sales conditional on demand/rules/licenses
```

Expected reasoning:

```text
Structured/reported amount may be Tier A/B.
Management explanation is a separate interpretation.
Future sales can have high semantic support but remain Tier C potential.
Do not relabel charge as lost revenue without explicit evidence.
```

### Batch 3 — AMD/TSMC relation trust

Review independently:

```text
source issuer
counterparty identity
relation direction
foundry role
product/process scope
current versus planned state
```

Do not create TSM issuer-side facts from AMD evidence.

### Batch 4 — AVGO trust semantics

Review:

```text
VCF product hierarchy
anonymous customer concentration
AI Revenue PSU plan adoption
future target achievement
```

Plan adoption may be occurred governance fact. Target achievement remains conditional potential and is not ordinary revenue guidance.

### Batch 5 — NVDA temporal trust

Review:

```text
earlier H20 expected charge
later H20 recorded charge
supply-chain role decomposition
```

Both filings can be trustworthy records of their own historical states. The later actual does not upgrade the earlier estimate at the earlier timestamp.

### Batch 6 — GOOGL/META/AMZN attribution trust

```text
GOOGL: decision/order versus allegation and future financial effect
META: Llama strategy as management interpretation, not monetization fact
AMZN: 13F reported holding only; no commercial or strategic inference
```

## Mandatory challenger review

Require a separate challenger when:

- inference_depth >= 2;
- a named supplier/customer/foundry/government/competitor is involved;
- contradiction_state is not `none`;
- economic truth is upgraded beyond `issuer_attested` without structured corroboration;
- potential changes to occurred or resolves a prior record;
- actual/guidance, GAAP basis, segment, period, unit, or scale changes;
- a material graph relation is Tier C or D;
- taxonomy affects multiple issuers.

The creator cannot approve its own candidate.

## Hard failure conditions

Reject the entire batch when any is non-zero:

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
source_evidence_mutation
accepted_status_emitted
```

## Completion

The stage is complete only when:

- deterministic source records are unchanged;
- every review record is atomic and replayable;
- every trust dimension is populated;
- attribution, inference premises, and bridge are explicit;
- evidence independence is assessed correctly;
- historical PIT states are preserved;
- Schema validation passes;
- manifest counts reconcile;
- challenger requirements are satisfied;
- all outputs remain `review_required` pending promotion.

# Local Agent Instruction — SEC Trust and Promotion Review

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

Do not edit the source metadata parquet, raw SEC evidence, filing identity, XBRL facts, tables, evidence snippets, hashes, timestamps, or accepted deterministic records.

The LLM stage is not a parser, filing summarizer, or investment analyst. It reviews only routed semantic residue.

## Mandatory files

Read in order:

```text
.agents/skills/sec-llm-semantic-review/SKILL.md
.agents/skills/sec-llm-semantic-review/references/PIT_POLICY.md
.agents/skills/sec-llm-semantic-review/references/TRUST_SEMANTICS_POLICY.md
.agents/skills/sec-llm-semantic-review/references/LLM_ROUTING_POLICY.md
.agents/skills/sec-llm-semantic-review/references/FINANCIAL_SEMANTIC_POLICY.md
.agents/skills/sec-llm-semantic-review/references/POTENTIAL_EVENT_POLICY.md
.agents/skills/sec-llm-semantic-review/references/REVIEW_OUTPUT_CONTRACT.md
.agents/skills/sec-llm-semantic-review/references/UPLOADED_ARCHIVE_CASEBOOK.md
.agents/skills/sec-llm-semantic-review/assets/review_batch_prompt.md
.agents/skills/sec-llm-semantic-review/assets/llm_review_record.schema.json
```

Routing queries:

```text
.agents/skills/sec-llm-semantic-review/assets/select_llm_routing_candidates.sql
.agents/skills/sec-llm-semantic-review/assets/select_trust_review_candidates.sql
.agents/skills/sec-llm-semantic-review/assets/select_potential_event_candidates.sql
```

## Two independent axes

Never conflate:

```text
promotion_level
  deterministic admission and LLM-routing state

trust_tier
  epistemic quality of one reviewed semantic representation
```

A management estimate may have:

```text
promotion_level = C
semantic_support_score = 0.97
trust_tier = C
economic_truth_status = not_independently_assessed
```

That means the evidence strongly supports “management made this estimate.” It does not imply a 97% event probability.

## Promotion routing contract

```text
A  -> formal library; 0% normal LLM
B  -> formal library; replayable 1%-5% audit, higher for configured high-impact relations
C  -> review_required; 100% mandatory by evidence group
D1 -> grouped mandatory review
D2 -> aggregate, deduplicate, rank, then review within budget
D3 -> retain evidence; no default LLM
R  -> deterministic rejection; replayable 0.1%-1% rejection-rule audit
```

Never create a queue equivalent to:

```sql
WHERE promotion_level != 'A'
```

### A

Do not send to LLM. A requires structured or fully constrained deterministic evidence.

### B

Already admitted to the formal library. LLM is an audit, not a rewrite stage.

Expected audit outcome:

```text
no_change
or
keep_formal_B
```

A B audit may recommend a change only with concrete subject, direction, role, scope, polarity, attribution, or PIT evidence and must route to challenger review.

### C

Review every eligible evidence group. Typical reasons:

- pronoun/passive binding;
- several companies in one sentence;
- relation direction or role ambiguity;
- product/segment/geography scope ambiguity;
- negation, condition, plan, estimate, or future tense;
- issuer versus third-party attribution;
- actual/estimate/risk/interpretation decomposition.

### D1

Review every deduplicated high-value evidence group, including:

- 10-K Item 1, Item 1A, Item 7;
- 10-Q risk or MD&A;
- supplier/customer/competitor/investment/foundry/action language;
- issuer-first-person language;
- quantified context;
- resolved listed or governed important entity;
- repeated high-value target across filings.

### D2

Do not review row by row. Aggregate and prioritize by:

```text
issuer
+ target entity
+ section role
+ normalized sentence hash
+ fiscal quarter/year bucket
```

Preserve every source evidence ID and PIT time.

### D3

No default review. Examples:

- proxy biography former employers;
- offering underwriter lists;
- legal definitions;
- signature pages;
- trademarks, addresses, email domains;
- references or reproduced news text;
- context-free ticker/name tables.

### R

No normal review. Audit only a small deterministic sample by rejection rule version.

A false-rejection finding creates:

```text
promotion_recommendation = rule_regression_candidate
```

It does not directly admit the record.

## Evidence group is the request unit

One LLM request must contain one governed evidence sentence/snippet and every candidate generated from it.

Stable group material:

```text
issuer_id
+ filing_id/accession
+ section_id or section_role
+ normalized evidence sentence hash
```

Example request:

```json
{
  "evidence_group_id": "stable-id",
  "issuer": "AMD",
  "form": "10-K",
  "section_role": "issuer_risk",
  "primary_evidence_id": "evidence-id",
  "candidate_ids": ["candidate-1", "candidate-2"],
  "mentioned_entities": ["Intel", "NVIDIA"],
  "candidate_topics": ["competition", "customer_concentration"]
}
```

The model may return several atomic decisions, but every JSONL record must reference the same `evidence_group_id` and relevant candidate IDs.

Never send the same sentence once for Intel, once for NVIDIA, and once per topic.

## Mandatory trust profile

Every output record requires:

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

Compatibility invariant:

```text
confidence == trust_profile.semantic_support_score
```

Confidence is not truth probability, event probability, investment conviction, materiality, or expected return.

## Preflight

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

Do not begin review unless deterministic validation passes.

## Freeze and record the batch

Record:

```text
signal_timestamp
run_id
batch_id
promotion policy version = promotion-routing-v1
promotion-level population counts
promotion-level selected counts
LLM-route counts
evidence-group count
candidate-row count
deduplicated count
candidate SQL and SHA-256
source database SHA-256
model/version/temperature
prompt SHA-256
taxonomy version
trust policy version = trust-semantics-v1
```

For B/R samples also record:

```text
rule ID/version
sample rate
sample seed or deterministic hash rule
population count
sample count
strata
sample reason
```

Sampling must be replayable.

## Select and build queues

Use:

```text
select_llm_routing_candidates.sql
```

The scheduler must:

1. exclude A;
2. select a deterministic B audit sample rather than the full B population;
3. include all eligible C evidence groups;
4. group D by evidence before any call;
5. include all deduplicated D1 groups;
6. rank/deduplicate D2 before budget selection;
7. exclude D3 by default;
8. select only a stratified R rule-audit sample.

## Semantic review workflow

### 1. Verify routing and evidence

Require:

```text
input_promotion_level
llm_route
evidence_group_id
candidate_ids
section_role
rule ID/version
source SHA-256
source_available_at
```

Reject invalid route/group membership before semantic reasoning.

### 2. Freeze PIT

Use only:

```text
source_available_at <= signal_timestamp
```

Date-only evidence is not intraday eligible. Later filings, prices, returns, news, and outcomes are forbidden.

### 3. Identify attribution

Choose:

```text
structured_sec_fact
issuer_reported_statement
management_estimate
management_interpretation
third_party_statement_in_filing
legal_or_regulatory_assertion
reviewer_inference
```

SEC provenance proves what was filed, not that every forecast, explanation, allegation, or risk is objectively true.

### 4. Audit inference

```text
0 direct structured/explicit
1 controlled normalization
2 composition of explicit premises
3 unstated bridge/reviewer inference
```

For depth 2/3:

- list every premise evidence ID;
- write the bridge explicitly;
- require challenger review;
- use `no_change` when another reasonable bridge exists.

Forbidden hidden bridges:

- co-mention;
- same industry;
- temporal sequence;
- embedding similarity;
- later stock response;
- later filing outcome;
- external knowledge outside the batch.

### 5. Assess corroboration

These are one information event, not independent corroboration:

- repeated wording;
- several snippets from one sentence;
- several candidates generated from one sentence;
- a deterministic candidate and its source evidence;
- an 8-K and attached issuer press release;
- copies of the same release across exhibits.

### 6. Separate occurred and potential

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

A later actual event creates a new record linked through `resolves_prior_review_id`. Never rewrite the earlier state.

### 7. Assess economic truth conservatively

```text
structurally_reported
issuer_attested
internally_corroborated
attributed_only
not_independently_assessed
contradicted_by_eligible_evidence
not_applicable
```

Do not emit `verified_true` or `proven_true`.

### 8. Derive trust tier

```text
A structurally verified and semantically direct
B explicit issuer/official assertion; may remain issuer-attested
C estimate, interpretation, attributed/legal statement, potential event, bounded composition
D inference, ambiguous scope/direction, unresolved material conflict
X integrity/PIT failure
```

Trust tier is not promotion level.

### 9. Recommend promotion

Allowed:

```text
keep_formal_B
promote_candidate_to_B
retain_C_or_D_review
reject_to_R
rule_regression_candidate
no_change
```

The LLM cannot mint A.

Promotion from C/D to B and any proposed change to B require challenger review and later validator/human approval.

## Output

Write:

```text
data/sec_yfinance/reviews/<RUN_ID>/<BATCH_ID>/records.jsonl
```

Also write:

```text
manifest.json
candidate_query.sql
candidate_query.sha256
validation.json
challenger_records.jsonl   # when required
```

Validate every line against:

```text
.agents/skills/sec-llm-semantic-review/assets/llm_review_record.schema.json
```

All new/corrected records remain:

```text
status = review_required
```

## Controlled company examples

### MU

- HBM4 sample delivery may be deterministic B or C depending on extraction completeness.
- Sampling occurred does not imply volume production.
- Repeated product mentions are not corroboration.

### AMD

- Explicit “rely on TSMC for wafer production” may be B and sampled, not mandatory LLM.
- MI308 paragraph is C because actual charge, rule, license status, and future conditional sales must be separated.
- A multi-company competition sentence is reviewed once as C/D1, not once per company.

### AVGO

- Compensation-plan adoption and future target achievement are separate.
- Proxy biography employer mentions route D3.
- Anonymous customer concentration never receives guessed identities.

### NVDA

- Earlier H20 estimate and later actual are separate historical states.
- Supply-chain co-mentions do not establish role without explicit direction/scope.

### GOOGL

- Court decision/order may be issuer/official procedural fact.
- Allegations remain attributed.
- Future implementation/financial effect remains potential unless realized.

### META

- Llama strategy may be management interpretation.
- Do not infer monetization, causality, or revenue materiality.

### AMZN

- Exact 13F rows bypass LLM as A.
- Only incomplete identity normalization enters review.
- Never infer commercial or strategic relations from holdings.

## Challenger requirements

Require an independent challenger when:

- inference depth >= 2;
- a B audit proposes a change;
- C/D is recommended for B promotion;
- a named high-impact relation is not deterministic B;
- contradiction state is not `none`;
- potential becomes occurred or resolves a prior record;
- actual/guidance, GAAP basis, segment, period, unit, or scale changes;
- economic truth is upgraded beyond issuer-attested without structured corroboration;
- an R audit finds possible over-rejection;
- taxonomy affects multiple issuers.

The creator cannot approve its own candidate.

## Hard failures

Reject the batch for:

```text
all_non_A_sent_to_llm
A_sent_without_explicit_qa
B_population_sent_without_sampling
B_sampling_not_replayable
C_eligible_group_skipped
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
missing_trust_profile
confidence_score_mismatch
trust_tier_derived_from_score_only
sec_filing_treated_as_proof_of_economic_truth
duplicate_evidence_counted_as_independent
hidden_inference_bridge
unsupported_economic_truth_upgrade
later_outcome_used_to_regrade_history
pit_or_integrity_failure_not_tier_x
source_evidence_mutation
accepted_status_emitted
```

## Completion

Complete only when:

- routing, grouping, deduplication, and sampling are replayable;
- all eligible C/D1 groups are accounted for;
- deterministic source rows remain unchanged;
- every output is atomic and references its evidence group/candidate IDs;
- every trust dimension is populated;
- attribution, inference premises, and bridges are explicit;
- historical PIT states are preserved;
- Schema validation passes;
- manifest counts reconcile;
- challenger requirements are satisfied;
- all outputs remain `review_required` pending promotion.

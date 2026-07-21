# Promotion-Level LLM Routing Policy

## Purpose

This policy controls **which deterministic semantic candidates are sent to the LLM**. It is separate from the multidimensional `trust_profile`.

Two axes must never be conflated:

```text
promotion_level
  = deterministic ingestion and review routing state

trust_tier
  = epistemic quality of a specific reviewed semantic representation
```

A record may enter the formal library at promotion level B while its economic truth remains `issuer_attested`. A management estimate may be promotion level C and trust tier C even when the evidence-to-semantics mapping is very strong.

Do not implement routing as:

```sql
WHERE promotion_level != 'A'
```

The objective is not to make the LLM review every non-A record. The objective is to send the LLM only evidence for which deterministic extraction achieved high recall but cannot safely resolve financial meaning.

## Promotion levels

### A — deterministic formal admission

Definition:

- exact structured fact or fully constrained deterministic rule;
- issuer, subject, predicate, object, scope, polarity, tense, and allowed section are established;
- no material ambiguity remains.

Routing:

```text
formal_library = yes
llm_default = no
llm_rate = 0%
```

Examples:

- SEC accession and acceptance time;
- exact XBRL/table value with context;
- deterministic 13F row;
- direct relation whose complete role and scope are encoded by a validated strict rule.

A records may enter a separate non-LLM deterministic QA process. Do not use an LLM simply to confirm them.

### B — rule-based formal admission with risk-based audit

Definition:

```text
issuer subject clear
+ relation/event verb clear
+ target clear
+ positive actual/current grammar
+ allowed form and section
+ no unresolved scope blocker
```

Example:

```text
We rely on TSMC for wafer production.
```

This can deterministically support an issuer-side dependency/manufacturing relation without mandatory LLM review.

Routing:

```text
formal_library = yes
llm_default = sampled audit only
normal_sample_rate = configurable 1%-5%
high_impact_sample_rate = configurable and higher than normal
```

Increase sampling for:

- named customer, supplier, foundry, strategic investment, government, or competitor relations;
- a new deterministic rule version;
- a newly observed entity or alias;
- unusual form/section combinations;
- complex sentence structure despite a successful rule;
- material graph edges with broad downstream use.

B review is an audit, not a rewrite pass. The LLM should normally return `no_change`. It may flag a rule regression or propose supersession only with concrete evidence of subject, direction, scope, polarity, attribution, or PIT error.

### C — mandatory semantic review

Definition:

Deterministic extraction found a plausible high-value semantic candidate, but one or more financially material dimensions remain unresolved:

- pronoun or subject resolution;
- passive voice binding;
- multiple companies in one sentence;
- target or product scope ambiguity;
- negation, condition, plan, estimate, or future tense;
- issuer versus third-party attribution;
- relation direction or role ambiguity;
- actual versus estimate/risk/interpretation decomposition.

Routing:

```text
formal_library = no
status = review_required
llm_route = mandatory
review_rate = 100% of eligible evidence groups
```

C is mandatory at the **evidence-group level**, not once per candidate row.

### D — high-recall mention/candidate layer

Definition:

The deterministic layer found company mentions, topic co-occurrence, weak relation language, or other high-recall evidence that is not sufficient for formal promotion.

All D evidence may be retained as:

```text
assertion_type = external_company_mention
promotion_level = D1 | D2 | D3
status = review_required or retained_unreviewed
```

D must not be sent to the LLM row by row.

#### D1 — high priority, grouped mandatory review

Send after grouping when any applies:

- 10-K Item 1, Item 1A, or Item 7;
- 10-Q risk factors or MD&A;
- same sentence contains supplier/customer/competitor/investment/partner/foundry/action language;
- same sentence contains issuer-first-person language such as `we`, `our`, or `the company`;
- target repeats across filings;
- target is resolved in local symbol/entity metadata;
- target is a listed company or governed important private entity;
- a number, percentage, capacity, unit, contract term, or concentration statement is nearby;
- manufacturing, purchasing, sales, distribution, collaboration, licensing, financing, or investment action is present.

Routing:

```text
formal_library = no
llm_route = grouped_mandatory
review_rate = 100% of deduplicated D1 evidence groups
```

#### D2 — medium priority, aggregate and budget

Examples:

- company name with weak relation language;
- third-party industry comparison;
- product/ecosystem mention;
- repeated semantically similar sentences across filings;
- candidate value exists but immediate financial role is unclear.

Routing:

```text
formal_library = no
llm_route = aggregate_then_review
review_rate = budgeted after aggregation, deduplication, and prioritization
```

D2 is not mandatory row by row. The scheduler may rank groups by recurrence, section value, entity importance, relation-action proximity, quantified context, and novelty.

#### D3 — low priority, retained without normal LLM review

Examples:

- former employers in proxy biographies;
- offering underwriter lists;
- companies in legal definitions;
- exhibit signature pages;
- trademark notices, email domains, or addresses;
- references, citations, or reproduced news text;
- context-free ticker/name tables.

Routing:

```text
formal_library = no
llm_route = no_default_review
review_rate = 0% except targeted QA or explicit research request
```

### R — deterministic rejection with audit sampling

Definition:

The deterministic rule has established that the candidate should not be promoted, for example:

- self-target;
- explicit negation;
- explicitly hypothetical context under a relation rule that requires actual state;
- prohibited form/section;
- target entity absent from evidence;
- subject clearly belongs to a third party;
- multiple securities of the same issuer mistakenly treated as external entities;
- signature, definition, boilerplate, or other excluded context.

Routing:

```text
formal_library = no
llm_default = no
audit_sample_rate = configurable 0.1%-1% by rejection rule version
```

R audits test whether a rejection rule is overbroad. An audit failure creates a `rule_regression_candidate`; it does not directly admit the rejected record.

## Evidence-group review unit

One LLM request must correspond to one governed evidence group, not one candidate row.

### Primary request-group key

Use a stable key based on:

```text
issuer_id
+ filing_id/accession
+ section_id or section_role
+ normalized evidence sentence hash
```

All candidates generated from that evidence sentence must be bundled:

```json
{
  "evidence_group_id": "stable-id",
  "issuer": "AMD",
  "form": "10-K",
  "section_role": "issuer_risk",
  "primary_evidence_id": "evidence-id",
  "evidence": "stored governed sentence/snippet",
  "candidate_ids": ["candidate-1", "candidate-2"],
  "mentioned_entities": ["Intel", "NVIDIA"],
  "candidate_topics": ["competition", "customer_concentration"]
}
```

The LLM request may return several decisions, but every output JSONL record remains one atomic subject-predicate-object claim referencing the same `evidence_group_id`.

### Cross-filing D2 deduplication key

For D2 ranking and recurrence aggregation, use:

```text
issuer_id
+ target_entity_key
+ section_role
+ normalized_sentence_hash
+ fiscal quarter/year bucket
```

Keep all source evidence IDs and PIT times. Deduplication reduces review calls; it does not erase historical evidence.

## Section-role routing

Prefer semantic `section_role` over raw form alone.

High-value roles include:

```text
issuer_business
issuer_risk
issuer_mda
issuer_financial_note
issuer_material_event
issuer_regulatory
issuer_supply_chain
issuer_competition
```

Low-default-value roles include:

```text
proxy_biography
underwriter_list
legal_definition
signature_page
trademark_notice
reference_text
address_block
context_free_table
```

A high-value form can still contain a D3 section, and a lower-priority form can contain a high-value issuer statement. Route by both form and section role.

## Sampling governance

Sampling must be deterministic and replayable.

Every sampled B or R batch must record:

```text
rule_version
promotion_policy_version
sample_rate
sample_seed or deterministic hash rule
population_count
sample_count
strata
selection timestamp
```

Stratify at minimum by:

- rule ID/version;
- form group;
- section role;
- relation/event family;
- issuer size or market-cap bucket when available;
- named versus anonymous target;
- new versus previously observed entity.

Do not use a random, unrecorded ad hoc sample.

## Routing matrix

| Promotion level | Formal library | LLM route |
|---|---:|---|
| A | yes | none |
| B | yes | sampled/high-risk audit |
| C | no | mandatory by evidence group |
| D1 | no | grouped mandatory |
| D2 | no | aggregate/deduplicate/prioritize |
| D3 | no | no default review |
| R | no | rejection-rule QA sample only |

Recommended policy ranges:

```text
A  = 0% LLM
B  = 1%-5% normal audit; higher configurable rate for high-impact relations
C  = 100% of eligible evidence groups
D1 = 100% after evidence grouping and exact deduplication
D2 = budgeted after aggregation and priority scoring
D3 = 0% by default
R  = 0.1%-1% stratified rule audit
```

## Relationship to trust profile

`promotion_level` is an input/routing state. `trust_profile` is the reviewed epistemic assessment.

Examples:

- A structured XBRL fact: promotion A, trust tier A.
- Explicit issuer relation admitted by a strict rule: promotion B, often trust tier B.
- Explicit management forecast: promotion C, potentially semantic score 0.97, trust tier C.
- Ambiguous multi-company sentence: promotion C or D1, trust tier determined after review.
- Ordinary proxy employer mention: promotion D3, no default trust review.
- Self-target rejection: promotion R, audited only by sample.

The LLM cannot mint promotion level A. A requires a deterministic, reproducible rule or structured source. The LLM may recommend:

```text
keep_formal_B
promote_candidate_to_B
retain_C_or_D_review
reject_to_R
rule_regression_candidate
no_change
```

A deterministic validator or human approval step performs final promotion.

## Hard failures

Reject a routing batch when:

```text
all_non_A_sent_to_llm
candidate_row_used_as_request_unit_for_D
same_evidence_sent_repeatedly_without_grouping
B_full_population_sent_without_explicit_rule-validation run
C_eligible_group_skipped_without_error
D1_not_grouped
D2_not_deduplicated
D3_sent_by_default
R_used_as_normal_review_queue
sampling_not_replayable
promotion_level_confused_with_trust_tier
llm_directly_mints_A
```

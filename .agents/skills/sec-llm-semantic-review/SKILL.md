---
name: sec-llm-semantic-review
description: Review selected SEC semantic evidence after deterministic extraction. Separate multidimensional trust from deterministic promotion and LLM routing; apply A/B/C/D1/D2/D3/R routing, evidence-sentence grouping, PIT controls, attribution, inference-chain audit, occurred-versus-potential classification, relation refinement, contradiction review, and append-only governed output. Do not parse raw filings, summarize whole filings, enrich from the web, review every non-A row, or collapse trust into one confidence score.
license: MIT
compatibility: Requires the Stock-Data-Fetcher SEC/Yfinance structured SQLite database and Python 3.11+.
metadata:
  author: pttangent
  version: "2026.07.21-trust-routing-v2"
---

# SEC LLM Semantic Review — Trust and Routing

## Purpose

This Skill handles only semantic residue left after deterministic SEC parsing and database validation.

It has two independent responsibilities:

```text
trust semantics
  = what the evidence supports, who said it, how much inference was used,
    whether it was PIT-eligible, and whether economic truth is established

LLM routing
  = which deterministic candidates should enter the formal library,
    mandatory review, grouped review, sampled audit, or no review
```

Never infer LLM routing from a single confidence threshold. Never send all records below A to the LLM.

The deterministic pipeline remains authoritative for filing identity, accession, form, SEC timing, document/section boundaries, XBRL facts, tables, 8-K Item families, 13F rows, hashes, offsets, and stored evidence snippets.

## Required reading

Read before every review batch:

1. `docs/SEC_YFINANCE_DAG_PIPELINE.md`
2. `docs/SOURCE_POLICY.md`
3. `references/PIT_POLICY.md`
4. `references/TRUST_SEMANTICS_POLICY.md`
5. `references/LLM_ROUTING_POLICY.md`
6. `references/FINANCIAL_SEMANTIC_POLICY.md`
7. `references/POTENTIAL_EVENT_POLICY.md`
8. `references/REVIEW_OUTPUT_CONTRACT.md`
9. `references/UPLOADED_ARCHIVE_CASEBOOK.md`

Use:

```text
assets/select_llm_routing_candidates.sql
assets/select_trust_review_candidates.sql
assets/select_potential_event_candidates.sql
assets/review_batch_prompt.md
assets/llm_review_record.schema.json
```

## Core doctrine

### SEC authority is narrow

An SEC filing is authoritative evidence that a document was filed, by whom, in what form, and when it became public. It does not automatically prove that:

- a forecast will occur;
- management's causal explanation is objectively correct;
- a legal allegation is true;
- a risk factor has realized;
- a named relationship has an assumed role or scope;
- a product mention proves shipment, production, qualification, revenue, or materiality.

### Trust is multidimensional

Every reviewed claim must include a `trust_profile`:

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

`confidence` is compatibility-only and must equal `semantic_support_score`. It is not event probability, management-truth probability, investment conviction, or economic truth.

### Promotion is a different axis

Every deterministic candidate has one `promotion_level`:

```text
A
B
C
D1
D2
D3
R
```

Routing contract:

```text
A  formal library; no LLM
B  formal library; 1%-5% replayable audit, higher for high-impact relations
C  review_required; 100% mandatory review by evidence group
D1 high-value mention evidence; grouped mandatory review
D2 aggregate, deduplicate, rank, and review within budget
D3 retain evidence; no default LLM
R  deterministic rejection; 0.1%-1% rule-audit sample only
```

`promotion_level` is not `trust_tier`. A management estimate may be promotion C, semantic score 0.97, and trust tier C. An explicit deterministic supplier relation may be promotion B and trust tier B.

## Actual archive scope

Validated uploaded archives currently cover:

```text
MU, AMD, AVGO, NVDA, AMZN, GOOGL, META
```

A standalone AAPL or TSM archive was not present in the validated set. TSM may be represented only as a counterparty explicitly described by another issuer. Do not create TSM issuer-side facts without TSM evidence.

## LLM activation boundary

Activate only through `LLM_ROUTING_POLICY.md`.

Normal routes:

- C: mandatory, but one request per evidence group;
- D1: mandatory after grouping and exact deduplication;
- D2: only after aggregation, deduplication, and priority/budget selection;
- B: deterministic replayable audit sample or explicit high-risk audit;
- R: small rejection-rule QA sample;
- A and D3: no default LLM.

Do not activate for raw parsing, exact table/XBRL values, generic summaries, excluded ownership forms, current-web enrichment, valuation, expected returns, trade recommendations, or alpha labels.

## Evidence group is the request unit

The LLM request unit is one governed evidence sentence/snippet, not one candidate row.

Primary grouping key:

```text
issuer_id
+ filing_id/accession
+ section_id or section_role
+ normalized evidence sentence hash
```

Bundle all candidate entities, relation hints, topics, and candidate IDs generated by that evidence:

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

One request may return several decisions, but each JSONL output remains one atomic claim and references the same `evidence_group_id`.

For D2 cross-filing aggregation, use:

```text
issuer_id
+ target_entity_key
+ section_role
+ normalized_sentence_hash
+ fiscal quarter/year bucket
```

Deduplication reduces LLM calls. It must preserve every evidence ID and PIT timestamp.

## Promotion routing details

### A

Direct structured or fully constrained deterministic result. Enter formal library. Do not send to LLM.

### B

Issuer, relation/event verb, object, polarity, actual/current grammar, and legal section are clear. Enter formal library. Review only by replayable sample or high-impact audit.

Example:

```text
We rely on TSMC for wafer production.
```

Do not make B a mandatory rewrite pass. The expected audit result is normally `no_change`.

### C

Material semantic ambiguity remains: pronoun/passive binding, multiple companies, scope, negation, condition, future state, third-party attribution, relation role/direction, or actual-versus-estimate decomposition. Review every eligible evidence group.

### D1/D2/D3

All external company mentions may be retained, but only valuable evidence reaches the LLM:

- D1: high-value issuer business/risk/MD&A/material-event evidence or strong financial-action context;
- D2: weak/repeated/ecosystem mentions, aggregated and ranked;
- D3: proxy biography, underwriter list, legal definition, signature page, trademark/address/reference/context-free table; no default review.

### R

Self-target, explicit negation, prohibited section/form, absent entity, third-party subject, same-issuer ticker confusion, or boilerplate rejection. Do not use R as a normal LLM queue. Audit a small stratified sample by rejection rule version.

## Required inputs

Each review request must include:

- frozen `signal_timestamp`;
- `promotion_level` and `llm_route`;
- stable `evidence_group_id`;
- all bundled `candidate_ids`;
- security, issuer, filing, accession, form, section role, and governed `source_available_at`;
- primary `evidence_id`, exact stored snippet, and source SHA-256;
- deterministic rule ID/version and routing policy version;
- only explicitly selected PIT-eligible corroborating or conflicting evidence;
- sampling metadata for B or R audits.

Reject the request if evidence identity, hash, availability, group membership, or routing decision cannot be reproduced.

## Review workflow

### 1. Freeze PIT and integrity

- Fix `signal_timestamp` before interpretation.
- Require evidence identity and source hash to match.
- Use only evidence available at or before the timestamp.
- Date-only evidence is not intraday eligible.
- Do not inspect later filings, amendments, prices, returns, news, or outcomes.

PIT/integrity failure requires `trust_tier = X`.

### 2. Verify routing

Before semantic review, confirm that the request belongs in the queue:

- A or D3 normally returns a routing error/no review;
- B must carry replayable sample/high-risk justification;
- C and D1 must not be skipped;
- D requests must be grouped by evidence sentence;
- R must carry rejection-rule audit metadata.

Do not continue when the scheduler sent every non-A row or duplicated the same evidence into several requests.

### 3. Identify who is speaking

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

Do not promote an attributed statement into an issuer-observed fact.

### 4. Reconstruct inference

Use:

```text
0 direct structured or explicit statement
1 controlled normalization or alias resolution
2 composition of explicit clauses/evidence
3 reviewer inference requiring an unstated bridge
```

List every premise. State the bridge for depth 2/3. Depth 3 cannot be automatically accepted. Co-mention, industry overlap, sequence, embeddings, later prices, and later outcomes are not valid hidden bridges.

### 5. Classify occurrence

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

Future states use `predicate = potential_event`. Confidence is never event probability.

### 6. Build trust profile

Apply `TRUST_SEMANTICS_POLICY.md`:

- repeated wording is not independent corroboration;
- an 8-K and its issuer press release are normally one information event;
- later confirmation does not upgrade an earlier historical state;
- structured values and management interpretation are separate claims;
- explicit issuer language may have high semantic support while economic truth remains `issuer_attested` or `not_independently_assessed`;
- direction, role, product scope, period, and geography are supported separately.

### 7. Apply financial logic

Preserve actual/estimate, stock/flow, GAAP/non-GAAP, consolidated/segment, currency, unit, scale, period, geography, product generation, lifecycle state, and direct/distributor/end-customer distinctions.

13F supports a reported quarter-end position, not transaction timing, purchase price, partnership, control, endorsement, or commercial relation.

### 8. Emit governed decisions

Allowed semantic action:

```text
accept
reject
supersede
create_candidate
no_change
taxonomy_candidate
```

Allowed promotion recommendation:

```text
keep_formal_B
promote_candidate_to_B
retain_C_or_D_review
reject_to_R
rule_regression_candidate
no_change
```

The LLM cannot mint A. A requires deterministic structured/direct validation. All new or corrected claims remain `review_required` until promotion by a validator or human reviewer.

## Trust tiers

```text
A = structurally verified and semantically direct
B = explicit issuer/official assertion with strong support; economic truth may remain issuer-attested
C = estimate, interpretation, attributed/legal statement, potential event, or bounded composition
D = reviewer inference, unresolved scope, or material contradiction
X = source-integrity or PIT failure
```

Trust tier is derived from the profile, never from numeric score alone.

## Challenger review

Require an independent challenger when:

- `inference_depth >= 2`;
- a named customer/supplier/foundry/government/competitor is involved and the result is not already deterministic B;
- a B audit proposes changing a formal record;
- a C/D candidate is recommended for promotion to B;
- occurrence changes from potential to occurred;
- contradiction state is not `none`;
- actual/guidance, GAAP basis, segment, period, unit, or scale changes;
- economic truth is stronger than `issuer_attested` without structured corroboration;
- taxonomy affects more than one issuer;
- an R audit finds a possible false rejection.

The creator cannot approve its own candidate.

## Completion gate

A batch is complete only when:

- routing and grouping are reproducible;
- sampling is replayable;
- source identity, hashes, and PIT eligibility reconcile;
- every output has `promotion_level`, `llm_route`, `evidence_group_id`, and candidate IDs;
- every record has a complete trust profile;
- `confidence == semantic_support_score`;
- duplicate evidence is not counted as corroboration;
- earlier knowledge states are preserved;
- A is never minted by LLM;
- all new/superseding claims remain `review_required`;
- JSON Schema and manifest validation pass;
- challenger requirements are satisfied.

Reject the batch for all-non-A routing, candidate-row D calls, ungrouped D1, undeduplicated D2, default D3 review, normal R review, unreplayable sampling, hidden inference, future evidence, source mutation, unsupported economic-truth upgrades, or confusion between promotion level and trust tier.

---
name: sec-llm-semantic-review
description: Re-evaluate the trust meaning of selected SEC semantic assertions after deterministic extraction. Use when the project must separate source integrity, issuer attribution, semantic support, inference depth, PIT eligibility, scope fidelity, contradiction state, and economic truth status. Also use for occurred-versus-potential events, relation refinement, disclosure deltas, and false-positive correction. Do not use for raw parsing, whole-filing summaries, external enrichment, investment advice, or collapsing trust into one confidence score.
license: MIT
compatibility: Requires the Stock-Data-Fetcher SEC/Yfinance structured SQLite database and Python 3.11+.
metadata:
  author: pttangent
  version: "2026.07.21-trust-semantics-v1"
---

# SEC LLM Semantic Review — Trust Semantics

## Purpose

This Skill reviews only the semantic residue left after deterministic SEC parsing and database validation.

Its primary task is **not to decide whether a company statement is true**. Its task is to represent exactly:

1. what evidence exists;
2. who made the statement;
3. what the statement explicitly supports;
4. what reasoning was required to normalize it;
5. when the statement became usable under PIT;
6. whether the claim is actual, ongoing, potential, hypothetical, attributed, or inferred;
7. whether eligible evidence conflicts with it.

The deterministic pipeline remains authoritative for filing identity, accession, form, SEC timing, document and section boundaries, XBRL facts, tables, 8-K Item families, 13F rows, hashes, offsets, and stored evidence snippets.

The LLM must never rewrite those records or use a later outcome to make an earlier assertion look more trustworthy.

## Required reading

Read in this order before every batch:

1. `docs/SEC_YFINANCE_DAG_PIPELINE.md`
2. `docs/SOURCE_POLICY.md`
3. `references/PIT_POLICY.md`
4. `references/TRUST_SEMANTICS_POLICY.md`
5. `references/FINANCIAL_SEMANTIC_POLICY.md`
6. `references/POTENTIAL_EVENT_POLICY.md`
7. `references/REVIEW_OUTPUT_CONTRACT.md`
8. `references/UPLOADED_ARCHIVE_CASEBOOK.md`

Use:

```text
assets/select_review_candidates.sql
assets/select_trust_review_candidates.sql
assets/select_potential_event_candidates.sql
assets/review_batch_prompt.md
assets/llm_review_record.schema.json
```

## Core doctrine

### SEC authority is narrow

An SEC filing is authoritative evidence that a document was filed, by whom, in what form, and when it became public. It does **not** automatically prove that:

- management's forecast will occur;
- management's causal explanation is objectively correct;
- a legal allegation is true;
- a risk factor has realized;
- a named relationship has the commercial scope the reviewer assumes;
- a product mention proves shipment, qualification, revenue materiality, or production status.

### Trust is multidimensional

Never describe a record only as “high confidence” or “low confidence.” Every review output must carry a `trust_profile` with separate dimensions:

```text
evidence_integrity
source_authority
statement_attribution
semantic_directness
inference_depth
temporal_eligibility
scope_fidelity
corroboration_state
contradiction_state
economic_truth_status
semantic_support_score
trust_tier
```

The old `confidence` field is retained only for compatibility and must equal `trust_profile.semantic_support_score`. It measures support for the semantic representation, not probability, investment conviction, or economic truth.

### Three different questions

For every claim, answer separately:

1. **Can the evidence be trusted as an authentic, time-governed source record?**
2. **Does the evidence support this exact semantic representation?**
3. **Does the project independently know the underlying economic claim is true?**

A filed management estimate may score highly on questions 1 and 2 while remaining `not_independently_assessed` on question 3.

## Actual archive scope

Validated uploaded archives currently cover:

```text
MU, AMD, AVGO, NVDA, AMZN, GOOGL, META
```

A standalone AAPL or TSM archive was not present in the validated set. TSM may be represented only as a counterparty explicitly described by another issuer. Do not create TSM issuer-side facts without TSM evidence.

## Activation boundary

Activate only for selected records requiring at least one of these decisions:

1. **Trust-profile reconstruction** — a record currently has only `confidence` or an ambiguous `explicitness` label.
2. **Attribution separation** — issuer fact, management estimate, management interpretation, third-party statement, legal allegation, rule, or reviewer inference is unclear.
3. **Inference audit** — the result requires normalization, sentence composition, cross-evidence synthesis, relation-direction reasoning, or unstated causal reasoning.
4. **Occurred versus potential** — event state is happened, ongoing, announced, expected, conditional, hypothetical, or undetermined.
5. **Relation refinement** — subject, target, direction, role, product scope, process scope, or dependency scope is incomplete.
6. **Contradiction handling** — two PIT-eligible records conflict or a later record supersedes but must not rewrite an earlier state.
7. **Scope/comparability review** — period, segment, geography, GAAP basis, unit, lifecycle state, or disclosure scope differs.
8. **False-positive correction** — co-mention, self-relation, wrong subject, wrong direction, duplicated evidence, or overstated economic meaning.

Everything else bypasses LLM review.

Do not activate for raw SGML/HTML/XML/XBRL parsing, exact table values, generic summaries, excluded ownership forms, web enrichment, valuation, expected returns, trade recommendations, or alpha labels.

## Required inputs

Each review unit must include:

- frozen `signal_timestamp`;
- security, issuer, filing, accession, form, and governed `source_available_at`;
- one primary `evidence_id` and exact stored snippet;
- section/Item and source SHA-256;
- reviewed assertion/relation ID when applicable;
- deterministic extraction metadata;
- only explicitly selected PIT-eligible corroborating or conflicting evidence.

Reject the unit if evidence identity, source hash, or availability cannot be reproduced from the database.

## Review workflow

### 1. Freeze PIT and integrity

- Fix `signal_timestamp` before interpretation.
- Require source hash and evidence identity to match.
- Use only evidence available at or before the frozen timestamp.
- Do not inspect later filings, amendments, prices, returns, news, or outcomes.
- Date-precision evidence is not valid for intraday use.

A PIT or integrity failure produces `trust_tier = X` and the claim is unusable, regardless of semantic plausibility.

### 2. Identify who is speaking

Choose the exact attribution:

```text
structured_sec_fact
issuer_reported_statement
management_estimate
management_interpretation
third_party_statement_in_filing
legal_or_regulatory_assertion
reviewer_inference
```

Do not promote an attributed statement into an issuer-observed fact. A filing may accurately report that a regulator alleged something without proving the allegation.

### 3. Reconstruct the inference chain

Record explicit premises and the bridge rule. Use `inference_depth`:

```text
0 = exact structured field or direct explicit statement
1 = controlled normalization or entity alias resolution
2 = composition of explicit clauses or PIT-eligible evidence
3 = reviewer inference requiring an unstated bridge
```

Depth 3 cannot be automatically accepted. Return `review_required`, require challenger review, and use `no_change` when the bridge is not uniquely defensible.

Never hide inference inside polished prose.

### 4. Classify event occurrence

Every event-like claim requires one:

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

Future states use `predicate = potential_event`. Confidence is never an event probability.

### 5. Build the trust profile

Apply `references/TRUST_SEMANTICS_POLICY.md` exactly. Important rules:

- duplicated wording in the same filing is not independent corroboration;
- a primary filing and its attached press release are usually one issuer information event, not two independent sources;
- later confirmation does not increase the earlier record's historical trust tier;
- a structured number can be trusted as filed while its management interpretation remains unverified;
- explicit issuer language can have high semantic support but only `issuer_attested` economic truth status;
- relation direction and product scope must be supported separately.

### 6. Apply financial logic

Preserve actual versus estimate, stock versus flow, GAAP versus non-GAAP, consolidated versus segment, currency, unit, scale, period, geography, product generation, and lifecycle state.

13F supports a reported quarter-end position, not transaction date, purchase price, partnership, control, endorsement, or commercial relation.

### 7. Choose one action

```text
accept
reject
supersede
create_candidate
no_change
taxonomy_candidate
```

The LLM may recommend an action but cannot write `status = accepted`. New or corrected records remain `review_required` until a deterministic validator or human approval step promotes them.

### 8. Emit one atomic record

One JSONL line equals one subject-predicate-object claim, one primary evidence record, one occurrence state, and one trust profile.

Split records by counterparty, role, product, lifecycle state, occurred versus potential, actual versus estimate, period, segment, geography, unit, or accounting basis.

## Trust tiers

Trust tier is a routing label, not a substitute for the dimensions:

```text
A = structurally verified and semantically direct
B = explicit issuer/official assertion with strong semantic support, economic truth not independently established
C = estimate, interpretation, attributed/legal statement, or bounded multi-clause composition
D = reviewer inference, unresolved scope, or material contradiction
X = source integrity or PIT failure; unusable
```

A lower tier is not necessarily less useful. A management estimate may be economically important while correctly remaining Tier C.

## Mandatory challenger review

Require an independent challenger when:

- `inference_depth >= 2`;
- trust tier is C or D for a named supplier/customer/foundry/government/competitor;
- occurrence changes from potential to occurred;
- a later record resolves a prior potential event;
- contradiction state is not `none`;
- actual versus guidance, GAAP basis, segment, period, unit, or scale changes;
- economic truth status is stronger than `issuer_attested` without structured corroboration;
- taxonomy affects more than one issuer.

The creator cannot approve its own candidate.

## Completion gate

A batch is complete only when:

- source identity, hashes, and PIT eligibility reconcile;
- every record has a complete trust profile;
- `confidence == semantic_support_score`;
- confidence is not used as probability or truth score;
- attribution and inference premises are explicit;
- duplicate evidence is not counted as independent corroboration;
- earlier knowledge states are preserved;
- every new/superseding record remains `review_required`;
- JSON Schema and batch-manifest validation pass;
- challenger requirements are satisfied.

Reject the batch for missing trust dimensions, invented corroboration, hidden inference, future evidence, source mutation, unsupported economic-truth upgrades, or any attempt to collapse multidimensional trust into one score.

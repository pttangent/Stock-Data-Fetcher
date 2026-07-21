---
name: sec-llm-semantic-review
description: Review only the ambiguous semantic residue left after the project's deterministic SEC pipeline has parsed and structured filings. Use for product lifecycle, occurred-versus-potential event separation, relation-role refinement, actual-versus-estimate decomposition, risk realization, disclosure deltas, segment comparability, legal remedies, and controlled taxonomy candidates. Do not use for raw parsing, XBRL/table extraction, generic summaries, external enrichment, or investment advice.
license: MIT
compatibility: Requires the Stock-Data-Fetcher SEC/Yfinance structured SQLite database and Python 3.11+.
metadata:
  author: pttangent
  version: "2026.07.21-project-cases-v3"
---

# SEC LLM Semantic Review

## Purpose

This is a **narrow post-processing reviewer** for semantic residue that deterministic extraction cannot safely resolve.

The deterministic pipeline remains authoritative for filing identity, SEC timing, document splitting, Item/section boundaries, tables, XBRL facts, 8-K Item families, 13F holdings, source hashes, offsets, and stored short evidence.

The LLM must not re-read raw filings as unconstrained documents, regenerate facts already structured, or produce generic company reports. It reviews only selected database evidence.

## Required reading

Before every batch, read:

1. `docs/SEC_YFINANCE_DAG_PIPELINE.md`
2. `docs/SOURCE_POLICY.md`
3. `references/PIT_POLICY.md`
4. `references/FINANCIAL_SEMANTIC_POLICY.md`
5. `references/POTENTIAL_EVENT_POLICY.md`
6. `references/REVIEW_OUTPUT_CONTRACT.md`
7. `references/UPLOADED_ARCHIVE_CASEBOOK.md`

Use:

```text
assets/select_review_candidates.sql
assets/review_batch_prompt.md
assets/llm_review_record.schema.json
```

## Actual archive scope

Validated uploaded archives currently cover:

```text
MU, AMD, AVGO, NVDA, AMZN, GOOGL, META
```

A standalone AAPL or TSM archive was not present. TSM may be reviewed only as a counterparty explicitly described by AMD or NVIDIA. Do not create TSM issuer-side facts until TSM's own archive is imported.

## Activation boundary

Activate only for selected records requiring one of these decisions:

1. **Product lifecycle:** sample, qualification, launch, volume production, shipment, ramp, majority of shipments, roadmap, phase-out.
2. **Occurred versus potential event:** distinguish happened, ongoing, announced, expected, conditional, hypothetical, or undetermined states.
3. **Mixed claim decomposition:** one evidence window contains actual facts, estimates, rules, risks, and management interpretation.
4. **Relation refinement:** explicit generic relation needs direction, role, product scope, process scope, or dependency scope.
5. **Disclosure delta:** comparable PIT-eligible filings need semantic change classification.
6. **Segment/accounting comparability:** reporting structure, retrospective recast, GAAP basis, segment scope, or period basis changed.
7. **Legal/regulatory meaning:** separate rule, remedy, obligation, realized impact, estimate, and unresolved uncertainty.
8. **Taxonomy governance:** controlled product family, generation, alias, platform hierarchy, or relation-class candidate.
9. **False-positive correction:** self-relation, co-mention relation, wrong subject/direction, duplicate, or overstated scope.

Do not activate for raw parsing, exact structured facts, generic summaries, ownership forms excluded by policy, current-web enrichment, trade recommendations, alpha labels, or valuation conclusions.

## Candidate selection gate

Do not send all assertions to the LLM. A review unit must come from an explicit candidate query and satisfy at least one condition:

```text
status = review_required
confidence < configured threshold
explicitness = estimated or inferred
generic relation lacks role or product scope
product lifecycle language coexists with a known product
future/modal language describes a possible event
actual/guidance/risk classes coexist in one evidence window
comparable prior filing exists and delta review was requested
segment/accounting scope changed
governance validator flagged the record
```

Everything else bypasses LLM review.

## Required inputs

Each review unit must include:

- frozen `signal_timestamp` or `as_of`;
- `security_id`, `issuer_id`, symbol;
- `filing_id`, accession, form, `available_at`;
- one primary `evidence_id` and stored short snippet;
- section title, Item, source SHA-256;
- optional reviewed assertion/relation ID;
- only explicitly selected PIT-eligible comparison evidence.

Reject the unit if primary evidence cannot be traced to `evidence_snippet`.

## Review workflow

### 1. Freeze PIT

- Fix `signal_timestamp` before reading evidence.
- Use only governed database evidence available at or before that timestamp.
- Do not inspect later filings, amendments, prices, returns, outcomes, or later taxonomy states.
- Record every evidence ID used.

### 2. Classify source meaning

Choose exactly one `claim_class`:

```text
reported_fact
management_estimate
risk_hypothesis
policy_or_rule
management_interpretation
third_party_statement
reviewer_inference
```

Never turn a risk into a realized fact or a management explanation into independently verified truth.

### 3. Classify occurrence state

Every record requires one `occurrence_status`:

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

Future/potential states must use:

```text
predicate = potential_event
```

Examples:

- MU delivered HBM4 samples: sampling `occurred`; HBM4 volume production not established.
- AMD recorded approximately $800M MI308-related charges: `occurred`.
- AMD future China sales depend on demand/rules/licenses: `conditional_potential`.
- NVIDIA expected up to $5.5B H20 charges: `expected_not_occurred` at that filing time.
- Later NVIDIA reported $4.5B charges: new `occurred` record; do not rewrite the earlier estimate.
- AVGO AI Revenue compensation target achievement: `conditional_potential`, not actual revenue.

Read `references/POTENTIAL_EVENT_POLICY.md` before reviewing event-like language.

### 4. Apply form-specific logic

- **10-K / 20-F / 40-F:** business, products, segments, supply chain, competition, concentration, commitments, annual risks.
- **10-Q:** quarter change, updated risk, MD&A, liquidity, working capital, inventory, segment restatement, guidance change.
- **8-K / 6-K:** Item code remains authoritative; review event decomposition and meaning only.
- **13F-HR:** identifier/alias normalization and position-state description only; no commercial relation or trade timing.
- **Proxy:** governance, compensation metric, voting proposal, board, auditor, related party.
- **SD / CORRESP / UPLOAD:** regulatory process, conflict minerals, SEC comment/response, disclosure commitment.
- **S-1 / S-3 / S-4 / 424B* / FWP:** instrument, offering structure, proceeds, dilution, distribution, deal terms.

### 5. Choose one action

```text
accept
reject
supersede
create_candidate
no_change
taxonomy_candidate
```

The LLM may recommend but cannot directly create an accepted database fact. Every new or corrected claim remains `review_required` until deterministic validation or human approval.

### 6. Emit atomic claims

One JSONL line equals one subject-predicate-object claim and one primary evidence record.

Split by counterparty, role, product/generation, occurred versus potential, actual versus estimate, period, geography, segment, or accounting basis.

Example:

```text
AMD --foundry_for--> TSMC
product_scope = HPC, FPGA, Adaptive SoC wafer production
occurrence_status = not_applicable
```

Do not combine TSMC, GlobalFoundries, UMC, and Samsung into one relation.

### 7. Check comparability and contradiction

- Compare like form, section, period, currency, unit, accounting basis, and segment scope.
- Distinguish balance-sheet stocks from period flows.
- Distinguish actual values from estimates, targets, and guidance.
- Distinguish GAAP from non-GAAP.
- Distinguish direct customer, distributor, contract manufacturer, and end customer.
- Do not call absence `removed` without equivalent scope.
- Preserve historical knowledge states; never select the version that later proved correct using hindsight.

### 8. Emit governed output

Follow `references/REVIEW_OUTPUT_CONTRACT.md` exactly. Write append-only JSONL outside authoritative source tables. Never modify source snippets, hashes, filing times, deterministic rows, or original accepted assertions.

## Project evidence hierarchy

Use only project-governed evidence:

1. structured SEC/XBRL/XML/table record;
2. explicit issuer statement in a filed document/exhibit;
3. issuer estimate, guidance, risk statement, or management interpretation;
4. reviewer inference from supplied PIT-eligible project evidence.

Do not browse or add external evidence in this review stage.

## Relation rules

A relation requires explicit subject, target, direction, role, and evidence.

Permitted refinement families:

```text
foundry_for
memory_supplier_for
assembly_test_for
packaging_provider_for
component_supplier_for
customer_of
distributor_for
competes_with
licensed_from
licensed_to
restricted_by
reported_holding_in
```

Hard prohibitions:

- never guess anonymous Customer A/B/C/D identities;
- never turn co-mention into a relation;
- never turn 13F holdings into commercial relations, control, or endorsement;
- never treat a competitor's action as the issuer's action;
- never create self-relations;
- never infer causality from sequence alone;
- never create issuer-side facts for a counterparty from another issuer's filing.

## Quantitative rules

- Prefer XBRL/table values over narrative numbers.
- Preserve raw value, currency, unit, scale, period, segment, GAAP/non-GAAP, and actual/guidance status.
- Never silently rescale thousands, millions, percentages, basis points, shares, or per-share values.
- Derived calculations require formula, input IDs, units, and calculation timestamp.
- Do not compare fiscal quarters by label alone when calendars differ.
- 13F position data does not reveal trade date or purchase price.
- Confidence is not an event probability.

## PIT hard gate

A claim is unusable when source availability is missing, evidence is later than the signal timestamp, report date is treated as availability, later filings rewrite earlier states, date-only evidence is used intraday, live use ignores observed/processed time, or future outcomes influenced classification.

## Confidence policy

- `0.98-1.00`: exact structured record or explicit unambiguous statement.
- `0.90-0.97`: explicit statement requiring controlled normalization.
- `0.75-0.89`: supported interpretation with limited ambiguity.
- `0.50-0.74`: plausible inference; retain `review_required` and require challenger.
- Below `0.50`: use `no_change`.

## Mandatory challenger review

A second independent reviewer is required when a claim names a supplier/customer/foundry/government/competitor; changes risk from hypothetical to realized; changes actual versus guidance; changes unit/scale/segment/GAAP/period; marks a delta removed/intensified/de-intensified; has confidence below 0.90; resolves a prior potential event; or proposes taxonomy affecting multiple issuers.

The creator cannot approve its own assertion.

## Completion gate

A batch is complete only when every record has valid evidence, candidate reason, occurrence status, PIT eligibility, unchanged source metadata, append-only history, units/scope, explicit limitations, model identity, prompt hash, taxonomy version, and replayable manifest.

Reject batches containing future evidence, source mutation, anonymous-identity guessing, missing occurrence status, potential stored as occurred, occurred stored as potential, later resolution rewriting prior state, invented probability, or invented event date.

---
name: sec-llm-semantic-review
description: Review only the ambiguous semantic residue left after the project's deterministic SEC pipeline has parsed and structured filings. Use for product lifecycle, relation-role refinement, actual-versus-estimate decomposition, risk realization, disclosure deltas, segment comparability, legal remedies, and controlled taxonomy candidates. Do not use for raw parsing, XBRL/table extraction, generic summaries, external enrichment, or investment advice.
license: MIT
compatibility: Requires the Stock-Data-Fetcher SEC/Yfinance structured SQLite database and Python 3.11+.
metadata:
  author: pttangent
  version: "2026.07.21-project-cases-v2"
---

# SEC LLM Semantic Review

## Purpose

This skill is a **narrow post-processing reviewer** for the semantic residue that deterministic extraction cannot safely resolve.

The deterministic pipeline remains authoritative for:

- filing identity, form, accession, report date, acceptance time, and governed availability;
- document and attachment splitting;
- Item/section boundaries;
- tables and XBRL facts;
- 8-K Item event family;
- 13F holdings;
- source hashes, offsets, and stored short evidence.

The LLM must not re-read the raw filing as an unconstrained document, regenerate facts already structured, or produce a general company report. It reviews selected database evidence only.

## Required reading

Before every review batch, read:

1. `docs/SEC_YFINANCE_DAG_PIPELINE.md`
2. `docs/SOURCE_POLICY.md`
3. `references/PIT_POLICY.md`
4. `references/FINANCIAL_SEMANTIC_POLICY.md`
5. `references/REVIEW_OUTPUT_CONTRACT.md`
6. `references/UPLOADED_ARCHIVE_CASEBOOK.md`

Use `assets/select_review_candidates.sql` to build a narrow candidate batch. Use `assets/review_batch_prompt.md` as the local-agent prompt template. Machine-readable output must conform to `assets/llm_review_record.schema.json`.

## Actual archive scope

The casebook currently covers uploaded and processed archives for:

```text
MU, AMD, AVGO, NVDA, AMZN, GOOGL, META
```

A standalone AAPL or TSM archive was not present in the validated upload set. TSM may be reviewed only as a counterparty explicitly described by AMD or NVIDIA. Do not create TSM issuer-side facts until a TSM archive is imported.

## Activation boundary

Activate this skill only when a selected record requires one of these decisions:

1. **Product lifecycle** — sampling, qualification, launch, volume production, shipment, ramp, majority of shipments, phase-out, or roadmap state.
2. **Mixed claim decomposition** — one evidence window contains actual facts, estimates, rules, risks, and management interpretation.
3. **Relation refinement** — a generic relation is explicit but needs precise direction, role, product scope, process scope, or dependency scope.
4. **Disclosure delta** — two comparable PIT-eligible filings need `new`, `removed`, `intensified`, `de_intensified`, `unchanged`, `wording_only`, or `not_comparable` classification.
5. **Segment/accounting comparability** — reporting structure, retrospective recast, GAAP/non-GAAP basis, segment scope, or period basis changed.
6. **Legal/regulatory meaning** — an event needs separation of rule, remedy, obligation, realized impact, estimate, and unresolved uncertainty.
7. **Taxonomy governance** — a product family, generation, alias, platform hierarchy, or relation class needs a controlled candidate.
8. **False-positive correction** — self-relation, co-mention relation, wrong subject, wrong direction, duplicated claim, or overstated scope.

Do not activate for:

- raw SGML, HTML, XML, Inline XBRL, table, or attachment parsing;
- facts already available in `xbrl_fact`, `filing_table`, `event_ledger`, or `form13f_holding`;
- simple topic or product-name mentions without ambiguity;
- generic whole-filing summaries;
- Forms 3, 4, 5, or 144 under the current policy;
- current-web enrichment or later news;
- BUY/SELL/HOLD, price targets, expected returns, alpha labels, or valuation conclusions.

## Candidate selection gate

Do not send all assertions to the LLM. A review unit must come from an explicit candidate query and satisfy at least one condition:

```text
status = review_required
confidence < configured threshold
explicitness = estimated or inferred
generic relation lacks product/role scope
product lifecycle language coexists with a known product
actual/guidance/risk classes coexist in one evidence window
comparable prior filing exists and delta review was requested
segment/accounting scope changed
governance validator flagged the record
```

Everything else bypasses the LLM.

## Required inputs

Each review unit must include:

- frozen `signal_timestamp` or `as_of`;
- `security_id`, `issuer_id`, and symbol;
- `filing_id`, accession, form, and `available_at`;
- one primary `evidence_id` and stored short snippet;
- section title, Item, and source SHA-256;
- optional deterministic `assertion_id` or `relation_id` being reviewed;
- only explicitly selected PIT-eligible comparison evidence.

Reject the unit if the primary evidence cannot be traced to `evidence_snippet`.

## Review workflow

### 1. Freeze PIT

- Fix `signal_timestamp` before reading evidence.
- Use only database evidence with governed availability at or before that timestamp.
- Do not inspect later filings, amendments, prices, returns, outcomes, or later taxonomy states.
- Record every evidence ID used.

### 2. Classify the source statement

Choose exactly one:

- `reported_fact`
- `management_estimate`
- `risk_hypothesis`
- `policy_or_rule`
- `management_interpretation`
- `third_party_statement`
- `reviewer_inference`

Never turn a hypothetical risk into a realized event or a management explanation into independently verified truth.

### 3. Apply form-specific logic

- **10-K / 20-F / 40-F:** business, products, segments, supply chain, competition, concentration, commitments, annual risks.
- **10-Q:** quarter change, updated risk, MD&A, liquidity, working capital, inventory, segment restatement, guidance change.
- **8-K / 6-K:** Item code remains authoritative; review only event decomposition and financial meaning.
- **13F-HR:** identifier/alias normalization and position-state description only; no commercial relation or trade-timing inference.
- **Proxy:** governance, compensation metric, voting proposal, board, auditor, related party.
- **SD / CORRESP / UPLOAD:** regulatory process, conflict minerals, SEC comment/response, disclosure commitment.
- **S-1 / S-3 / S-4 / 424B* / FWP:** instrument, offering structure, proceeds, dilution, distribution, and deal terms.

### 4. Decide one action

Choose exactly one:

- `accept`
- `reject`
- `supersede`
- `create_candidate`
- `no_change`
- `taxonomy_candidate`

The LLM may recommend but cannot directly write an `accepted` database fact. All new or corrected claims remain `review_required` until deterministic validation or human approval.

### 5. Emit atomic claims

One JSONL line must express one subject-predicate-object claim with one primary evidence record.

Split by:

- different counterparties;
- different relation roles;
- different products or generations;
- actual versus estimate;
- current state versus future risk;
- different reporting periods or segment scopes.

Example:

```text
AMD --foundry_for--> TSMC
product_scope = HPC, FPGA, Adaptive SoC wafer production
```

Do not combine TSMC, GlobalFoundries, UMC, and Samsung into one supplier assertion.

### 6. Run comparability and contradiction checks

Before returning a result:

- compare like form, section, period, currency, unit, accounting basis, and segment scope;
- distinguish balance-sheet stocks from period flows;
- distinguish actual values from estimates, targets, and guidance;
- distinguish GAAP from non-GAAP;
- distinguish direct customer, distributor, contract manufacturer, and end customer;
- do not call an absent disclosure `removed` unless equivalent scope is confirmed;
- preserve conflicting historical knowledge states rather than selecting one with hindsight.

### 7. Emit governed output

Follow `references/REVIEW_OUTPUT_CONTRACT.md` exactly.

Write append-only JSONL outside authoritative source tables. Never modify source snippets, source hashes, filing times, deterministic extraction rows, or original accepted assertions.

## Project evidence hierarchy

For this skill, use only evidence already governed by the project database:

1. structured SEC/XBRL/XML/table record;
2. explicit issuer statement in a filed primary document or exhibit;
3. issuer estimate, guidance, risk statement, or management interpretation;
4. reviewer inference from supplied PIT-eligible project evidence.

Do not browse or add external evidence during this review. External enrichment must be a separate future pipeline with its own source table, timestamps, and governance.

## Relation rules

A relation requires explicit subject, target, direction, role, and evidence.

Permitted refinement families include:

- `foundry_for`
- `memory_supplier_for`
- `assembly_test_for`
- `packaging_provider_for`
- `component_supplier_for`
- `customer_of`
- `distributor_for`
- `competes_with`
- `licensed_from` / `licensed_to`
- `restricted_by`
- `reported_holding_in`

Hard prohibitions:

- never guess Customer A/B/C/D identities;
- never turn co-mention into a relation;
- never turn a 13F holding into supplier, customer, partnership, control, or endorsement;
- never treat a competitor's action as the issuer's action;
- never create self-relations;
- never infer causality from sequence alone;
- never create issuer-side facts for a counterparty from another issuer's filing.

## Quantitative rules

- Prefer XBRL/table values over narrative numbers.
- Preserve raw value, currency, unit, scale, period, segment, GAAP/non-GAAP, and actual/guidance status.
- Never silently rescale thousands, millions, percentages, basis points, shares, or per-share values.
- Derived calculations require formula, input IDs, units, and calculation timestamp.
- Do not compare fiscal quarters by label alone when fiscal calendars differ.
- 13F position data does not reveal transaction date or purchase price.

## PIT hard gate

A claim is unusable if:

- source availability is missing;
- evidence is later than `signal_timestamp`;
- only report date or period end is treated as availability;
- a later amendment or filing rewrites an earlier state;
- date-precision evidence is used intraday;
- live use ignores `observed_at` and processing latency;
- future prices, returns, outcomes, or later filings influenced the semantic decision.

## Confidence policy

Confidence measures evidence-to-semantics support, not economic truth.

- `0.98-1.00`: exact structured record or explicit unambiguous statement;
- `0.90-0.97`: explicit statement requiring only controlled normalization;
- `0.75-0.89`: supported interpretation with limited ambiguity;
- `0.50-0.74`: plausible inference; retain `review_required` and require challenger review;
- below `0.50`: use `no_change`.

## Mandatory challenger review

A second independent reviewer is required when:

- a claim names a supplier, customer, foundry, government, or competitor;
- risk changes from hypothetical to realized;
- actual versus guidance classification changes;
- currency, unit, scale, segment, GAAP status, or period changes;
- delta is `removed`, `intensified`, or `de_intensified`;
- confidence is below 0.90;
- a taxonomy proposal affects more than one issuer.

The creator cannot approve its own new assertion.

## Completion gate

A review batch is complete only when:

- every record has a valid primary `evidence_id`;
- candidate selection reason is recorded;
- all evidence is PIT-eligible;
- source times and hashes are unchanged;
- original deterministic records remain present;
- every new/superseding claim is `review_required`;
- no anonymous identity is guessed;
- no quantitative value loses unit, period, scope, or accounting basis;
- contradictions and limitations are explicit;
- model identity, prompt hash, taxonomy version, and batch manifest are present;
- the batch can be replayed from stored IDs.

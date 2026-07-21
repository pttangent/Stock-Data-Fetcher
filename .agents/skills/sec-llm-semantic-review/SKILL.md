---
name: sec-llm-semantic-review
description: Review and correct deterministic SEC semantic assertions after structured ingestion while preserving point-in-time availability, source evidence, financial meaning, and append-only audit history. Use for ambiguous products, relations, risks, events, disclosure deltas, entity resolution, and taxonomy proposals. Do not use for raw filing parsing, XBRL extraction, unsupported investment advice, or rewriting source evidence.
license: MIT
compatibility: Requires the Stock-Data-Fetcher SEC/Yfinance structured SQLite database and Python 3.11+.
metadata:
  author: pttangent
  version: "2026.07.21"
---

# SEC LLM Semantic Review

## Purpose

This skill is a **post-processing reviewer**, not a primary extractor. The deterministic pipeline remains authoritative for filing identity, document splitting, Item/section boundaries, tables, XBRL facts, 8-K Item events, 13F holdings, hashes, and timestamps.

The LLM may review ambiguity and propose corrections, but it must never replace, delete, or silently mutate source evidence or deterministic accepted assertions.

## Required reading

Before performing any review, read:

1. `docs/SEC_YFINANCE_DAG_PIPELINE.md`
2. `docs/SOURCE_POLICY.md`
3. `references/PIT_POLICY.md`
4. `references/FINANCIAL_SEMANTIC_POLICY.md`
5. `references/REVIEW_OUTPUT_CONTRACT.md`

If reviewing a new taxonomy or relation class, also read `references/EXTERNAL_SKILL_REVIEW.md` to understand which public-skill patterns were adopted and rejected.

## Activation boundary

Use this skill only when at least one of the following is true:

- a deterministic assertion is `review_required`, low-confidence, contradictory, or likely a false positive;
- an entity alias, product family, relation direction, relation type, or product scope is ambiguous;
- a filing contains difficult narrative semantics not represented by XBRL or fixed rules;
- the task is to compare two PIT-eligible disclosures and classify the semantic delta;
- the task is to propose a taxonomy addition without automatically accepting it;
- the task is to explain why a deterministic assertion should be accepted, rejected, or superseded.

Do not activate for:

- parsing raw SEC SGML, HTML, XML, Inline XBRL, tables, or attachments;
- re-extracting values already available in `xbrl_fact` or `filing_table`;
- reading every filing merely to produce a generic company summary;
- generating BUY/SELL/HOLD recommendations or price targets;
- using Forms 3, 4, 5, or 144 unless the user explicitly changes the form policy;
- importing current web knowledge into a historical PIT review without a separately timestamped external evidence record.

## Inputs

Operate on database records, never on an ungoverned text dump. A review unit must include:

- `signal_timestamp` or `as_of`;
- `security_id`, `symbol`, and `issuer_id`;
- `filing_id`, accession, form, and `available_at`;
- one primary `evidence_id` and its exact short snippet;
- optional deterministic `assertion_id` being reviewed;
- section title, Item, and source SHA-256;
- any prior PIT-eligible comparison evidence explicitly supplied by the orchestrator.

Reject the task as incomplete if the primary evidence cannot be traced to an existing `evidence_snippet` row.

## Review workflow

### 1. Freeze the PIT universe

- Set `signal_timestamp` before reading evidence.
- Use only evidence whose governed usable time is not later than `signal_timestamp`.
- Do not inspect later filings, later amendments, later news, future prices, or later taxonomy labels.
- Record the IDs of every evidence row actually used.

### 2. Classify the source statement

Assign exactly one source-statement class:

- `reported_fact`: issuer reports an actual historical fact;
- `management_estimate`: estimate, outlook, target, or guidance;
- `risk_hypothesis`: conditional or hypothetical risk disclosure;
- `policy_or_rule`: law, regulation, license condition, accounting policy, or contractual rule;
- `management_interpretation`: management's explanation or causal narrative;
- `third_party_statement`: quoted, attributed, or described statement by another party;
- `reviewer_inference`: conclusion not explicitly stated in the evidence.

Never convert a risk hypothesis into a realized event, or a management interpretation into an independently verified fact.

### 3. Apply form-specific financial logic

- **10-K / 20-F / 40-F:** business model, products, segments, supply chain, competition, concentration, commitments, annual risks.
- **10-Q:** quarter-specific change, updated risk, MD&A, liquidity, working capital, inventory, guidance changes.
- **8-K / 6-K:** event type is anchored to Item code and filing availability; exhibits may contain earnings releases or agreements.
- **13F-HR:** a reported holding or investment relation only; never infer supplier, customer, partnership, control, or endorsement.
- **Proxy:** governance, compensation, voting proposal, board, auditor, and related-party semantics.
- **SD / CORRESP / UPLOAD:** regulatory process, conflict-minerals process, SEC comment/response, or disclosure commitment.
- **S-1 / S-3 / S-4 / 424B* / FWP:** financing instrument, offering structure, use of proceeds, dilution, distribution, and deal terms.

### 4. Decide the review action

Choose exactly one:

- `accept`: deterministic assertion is supported as written;
- `reject`: assertion is unsupported, misdirected, duplicated, self-referential, or semantically wrong;
- `supersede`: preserve the original assertion and propose a corrected replacement;
- `create_candidate`: propose a new assertion from supplied evidence;
- `no_change`: evidence is insufficient or ambiguity cannot be resolved safely;
- `taxonomy_candidate`: propose a new product/topic/entity alias or relation class for later governance review.

The LLM must not directly create an `accepted` database assertion. New or corrected claims remain `review_required` until deterministic validation or human approval.

### 5. Produce one atomic claim per record

A record must express one subject-predicate-object claim. Split mixed sentences into separate records when they contain different relations, periods, products, or confidence levels.

Examples:

- acceptable: `NVDA --depends_on_foundry--> TSMC`, product scope `advanced GPU wafers`;
- separate claim: `NVDA --depends_on_packaging_capacity--> CoWoS`;
- unacceptable combined claim: `NVDA relies on TSMC, Samsung, memory vendors, packaging and Asian suppliers`.

### 6. Run contradiction and comparability checks

Before returning a correction:

- compare like form, section, reporting scope, period, currency, unit, and accounting basis;
- distinguish consolidated from segment disclosure;
- distinguish point-in-time balances from period flows;
- distinguish actual results from guidance and non-GAAP measures;
- classify disclosure changes as `new`, `removed`, `intensified`, `de_intensified`, `unchanged`, or `wording_only`;
- do not treat absence as removal unless the comparison section has equivalent scope.

### 7. Emit the governed review record

Follow `references/REVIEW_OUTPUT_CONTRACT.md` exactly. Output JSONL only when the orchestrator requests machine-readable review records. Never write directly into source evidence tables.

## Evidence hierarchy

For claims inside this database, use this priority:

1. structured SEC fields, Inline XBRL, XML, and filing tables;
2. explicit issuer statement in the primary filing or filed exhibit;
3. issuer-attributed estimate, guidance, or risk statement;
4. separately governed official external source with its own availability timestamp;
5. high-quality secondary source, clearly marked external and never used to rewrite historical SEC evidence;
6. reviewer inference, always `inferred` and `review_required`.

A lower-ranked source cannot silently override a higher-ranked source. Conflicts must be preserved as separate assertions with a review note.

## Relation rules

A company relation requires an explicit subject, target, direction, and relation type.

Allowed automatic-review relation families include:

- `supplier_of`, `customer_of`, `foundry_for`, `assembly_test_for`, `memory_supplier_for`;
- `depends_on_capacity_of`, `licensed_from`, `licensed_to`, `distributes_for`;
- `competes_with`, `strategic_partner_with`;
- `invested_in` or `reported_holding_in` for structured 13F evidence;
- `regulated_by` or `restricted_by` for explicit rules or government actions.

Hard prohibitions:

- do not reveal or guess anonymous Customer A/B/C identities;
- do not turn co-mention into a relation;
- do not treat an investment as a commercial relationship;
- do not treat a competitor's action described in the filing as the issuer's action;
- do not create self-relations;
- do not infer causality from temporal sequence alone.

## Quantitative rules

- Prefer deterministic XBRL/table values over narrative numbers.
- Preserve currency, unit, scale, fiscal period, segment, GAAP/non-GAAP status, and actual/guidance status.
- Never silently rescale thousands, millions, percentages, basis points, shares, or per-share values.
- For 13F, preserve the value as reported under the applicable SEC schema; do not assume legacy thousands units.
- Derived calculations require an explicit formula, input IDs, units, and calculation timestamp.
- Do not compare fiscal quarters solely by label when fiscal calendars differ.

## PIT hard gate

A claim is unusable for research if any of these is true:

- `source_available_at` is missing;
- evidence becomes available after `signal_timestamp`;
- only `report_date` or period end is known;
- a later amendment was used to rewrite an earlier historical state;
- an intraday signal uses date-precision-only evidence;
- live use ignores local `observed_at` and processing latency;
- the review used later prices or outcomes to decide whether the original claim was "correct".

See `references/PIT_POLICY.md` for exact timing rules.

## Confidence policy

Confidence measures whether the proposed semantic representation is supported by the cited evidence, not whether the company statement is economically true.

- `0.98-1.00`: exact structured field or explicit unambiguous statement;
- `0.90-0.97`: explicit statement requiring only entity normalization;
- `0.75-0.89`: supported interpretation with limited ambiguity;
- `0.50-0.74`: plausible inference; keep `review_required`;
- below `0.50`: return `no_change` rather than create a claim.

## Completion gate

A review batch is complete only when:

- every output record has one valid primary `evidence_id`;
- all used evidence is PIT-eligible;
- source times and hashes are unchanged;
- original deterministic assertions remain present;
- every new/superseding claim is `review_required`;
- no anonymous entity was guessed;
- no quantitative value lost its unit, period, or accounting basis;
- contradictions and unsupported relations are explicitly flagged;
- the batch can be replayed from stored IDs, prompt hash, model identity, and version.

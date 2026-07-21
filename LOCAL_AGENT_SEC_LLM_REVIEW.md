# Local Agent Instruction — Post-SEC LLM Semantic Review

## Working boundary

Work only in:

```text
D:\DEV\AnotherNetworkFactory\SEC_Yfinance_Fetcher
```

Use branch:

```text
agent/equity-semantic-library-clean
```

Do not edit the source metadata parquet, raw SEC evidence, deterministic filing rows, XBRL facts, tables, evidence snippets, or existing accepted assertions.

The LLM review stage is **not** a second parser and **not** a whole-filing summarizer. It handles only selected semantic residue after the deterministic pipeline and database validation pass.

## Mandatory Skill files

Read in this order:

```text
.agents/skills/sec-llm-semantic-review/SKILL.md
.agents/skills/sec-llm-semantic-review/references/PIT_POLICY.md
.agents/skills/sec-llm-semantic-review/references/FINANCIAL_SEMANTIC_POLICY.md
.agents/skills/sec-llm-semantic-review/references/POTENTIAL_EVENT_POLICY.md
.agents/skills/sec-llm-semantic-review/references/REVIEW_OUTPUT_CONTRACT.md
.agents/skills/sec-llm-semantic-review/references/UPLOADED_ARCHIVE_CASEBOOK.md
.agents/skills/sec-llm-semantic-review/assets/review_batch_prompt.md
.agents/skills/sec-llm-semantic-review/assets/llm_review_record.schema.json
```

Candidate queries:

```text
.agents/skills/sec-llm-semantic-review/assets/select_review_candidates.sql
.agents/skills/sec-llm-semantic-review/assets/select_potential_event_candidates.sql
```

## Core distinction: fact versus potential

Every event-like review record must have one `occurrence_status`:

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

Use `predicate = potential_event` for:

```text
announced_not_occurred
expected_not_occurred
conditional_potential
hypothetical_risk
```

Examples:

```text
MU delivered HBM4 samples
  -> sampling occurred
  -> volume production not established

AMD recorded approximately $800M MI308-related charges
  -> occurred

AMD future China sales depend on licenses, import rules, and demand
  -> conditional_potential
  -> predicate = potential_event

NVDA expected up to $5.5B H20-related charges in April
  -> expected_not_occurred
  -> predicate = potential_event

NVDA later reported $4.5B charges in May
  -> new occurred record
  -> link resolves_prior_review_id to the April potential review
  -> never rewrite April as occurred

AVGO CEO PSU AI Revenue target
  -> adoption of compensation plan occurred
  -> achievement of target conditional_potential
  -> not actual revenue and not ordinary company guidance
```

## Review only these categories

- product lifecycle state;
- potential future events;
- mixed actual/estimate/risk/rule statements;
- generic relation-role or product-scope refinement;
- disclosure delta between comparable PIT-eligible filings;
- segment/accounting comparability change;
- legal/regulatory remedy and obligation decomposition;
- controlled taxonomy candidates;
- deterministic false-positive correction.

Everything else bypasses LLM review.

## Do not review

- raw filing documents;
- exact XBRL/table values;
- filing identity, accession, SEC timing, hashes, or Item boundaries;
- exact 13F holding rows unless identifier normalization is incomplete;
- all accepted assertions by default;
- Forms 3, 4, 5, or 144 under current policy;
- current web information;
- future prices, returns, outcomes, analyst ratings, or later filings outside the frozen PIT set;
- trade recommendations, expected return, alpha direction, or valuation conclusions.

## Batch preparation

1. Confirm deterministic pipeline validation is clean.
2. Set one frozen `signal_timestamp`.
3. Run one candidate SQL query.
4. Save the exact query and SHA-256 hash.
5. Materialize only selected IDs and stored short evidence.
6. Split by company and candidate reason.
7. Limit the first pass to a small controlled batch.

Recommended directory:

```text
data/sec_yfinance/reviews/<RUN_ID>/<BATCH_ID>/
```

Required outputs:

```text
records.jsonl
manifest.json
candidate_query.sql
candidate_query.sha256
validation.json
challenger_records.jsonl   # when challenger review is required
```

## First controlled review sequence

### Batch 1 — MU product lifecycle

Review:

```text
HBM3E 8-high volume production
HBM3E 12-high majority of HBM shipments
HBM4 36GB 12-high customer sampling
```

Expected separation:

```text
sampling occurred
volume production occurred only where explicitly stated
future qualification/ramp potential only when explicitly stated
no customer identity inference
```

### Batch 2 — AMD MI308

Separate:

```text
approximately $800M charge -> occurred
export-license requirement -> ongoing
some licenses granted -> occurred
future China sales -> conditional_potential
```

Do not store the charge as lost revenue. Do not store future sales as occurred.

### Batch 3 — AMD supply chain and segments

Review:

```text
AMD -> TSMC foundry role and product scope
AMD -> GlobalFoundries foundry role and node scope
AMD reportable-segment restructuring and retrospective recast
```

Do not create TSM issuer-side facts from AMD evidence.

### Batch 4 — AVGO

Review:

```text
VCF core platform versus optional services
anonymous end-customer concentration
AI Revenue PSU metric versus realized revenue
```

Keep compensation target achievement as potential.

### Batch 5 — NVDA

Review:

```text
H20 April estimate -> potential
H20 May actual charge -> occurred
estimate-to-actual link
foundry, memory, assembly/test, and packaging role decomposition
anonymous customer concentration
```

### Batch 6 — GOOGL, META, AMZN

Review:

```text
GOOGL court decision occurred versus remedy obligations ongoing
META Llama strategy without monetization inference
AMZN 13F alias normalization only when deterministic identifiers are incomplete
```

## Output contract

Each JSONL line must:

- conform to `llm_review_record.schema.json`;
- contain one atomic claim;
- reference one primary `evidence_id`;
- preserve database identity and source time exactly;
- include `candidate_reason` and `occurrence_status`;
- use `status = review_required`;
- record model, version, temperature, prompt hash, taxonomy version, and limitations;
- avoid pasted or rewritten evidence text.

## Challenger review

Require a second independent reviewer when:

- a supplier, customer, foundry, government, or competitor is named;
- a claim changes from potential to occurred;
- a later event resolves a prior potential event;
- actual versus guidance classification changes;
- amount, unit, scale, segment, GAAP basis, or period changes;
- delta is removed, intensified, or de-intensified;
- confidence is below 0.90;
- taxonomy affects more than one issuer.

The creator cannot approve its own assertion.

## PIT hard gate

Reject the entire batch when:

```text
source_available_at is missing
source_available_at > signal_timestamp
date-only evidence is used intraday
later filing rewrites an earlier knowledge state
future prices or outcomes were visible
external evidence was added
source evidence was mutated
```

## Potential-event hard gate

Reject the batch when:

```text
occurrence_status is missing
potential is stored as occurred
occurred is stored as potential
later resolution rewrites the prior potential record
future amount is stored as actual
conditional event has no stated condition
probability is invented
event date is invented
```

## Completion

The LLM stage is complete only when:

- deterministic source records remain unchanged;
- every review record is append-only and replayable;
- potential and occurred events are separately represented;
- all later resolutions link rather than overwrite;
- JSON Schema validation passes;
- challenger requirements are satisfied;
- manifest counts reconcile with JSONL output;
- all records remain `review_required` pending promotion.

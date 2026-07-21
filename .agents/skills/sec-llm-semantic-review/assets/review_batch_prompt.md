# Local Agent Prompt Template — SEC Trust-Semantic Review

Use this template only after deterministic SEC parsing, structured extraction, and database validation pass.

```text
You are performing a governed post-filing trust-semantic review for the Equity Semantic Library.

Repository:
D:\DEV\AnotherNetworkFactory\SEC_Yfinance_Fetcher

Branch:
agent/sec-llm-semantic-review-potential

Load and obey, in order:
.agents/skills/sec-llm-semantic-review/SKILL.md
.agents/skills/sec-llm-semantic-review/references/PIT_POLICY.md
.agents/skills/sec-llm-semantic-review/references/TRUST_SEMANTICS_POLICY.md
.agents/skills/sec-llm-semantic-review/references/FINANCIAL_SEMANTIC_POLICY.md
.agents/skills/sec-llm-semantic-review/references/POTENTIAL_EVENT_POLICY.md
.agents/skills/sec-llm-semantic-review/references/REVIEW_OUTPUT_CONTRACT.md
.agents/skills/sec-llm-semantic-review/references/UPLOADED_ARCHIVE_CASEBOOK.md

Database:
D:\DEV\AnotherNetworkFactory\SEC_Yfinance_Fetcher\data\sec_yfinance_structured.db

Candidate SQL:
.agents/skills/sec-llm-semantic-review/assets/select_trust_review_candidates.sql

Review scope:
- signal_timestamp: <ISO-8601 TIMESTAMP>
- run_id: <RUN_ID>
- batch_id: <BATCH_ID>
- candidate_reason: <ONE ALLOWED REASON>
- selection query hash: <SHA256>
- supplied assertion/relation/evidence IDs: <SCOPE>

Your task is not to decide whether management is honest and not to summarize filings. Review only selected deterministic assertions, relations, and stored evidence snippets.

For each record, answer three separate questions:
1. Is the evidence authentic, traceable, and PIT-eligible?
2. Does the evidence support this exact semantic representation?
3. Does the project independently know the underlying economic claim is true?

Never merge those questions into one confidence score.

Required steps for every record:
1. Verify evidence ID, filing/accession identity, source SHA-256, and source_available_at.
2. Reject evidence later than signal_timestamp. Date-only evidence is not intraday eligible.
3. Identify source_authority and statement_attribution.
4. Classify claim_class and occurrence_status.
5. Reconstruct inference_depth, inference_premises, and inference_bridge.
6. Assess scope_fidelity separately for entity, direction, product, period, segment, geography, GAAP basis, currency, unit, and scale.
7. Determine whether purported corroboration is independent. Repeated wording, several snippets from one sentence, and an 8-K plus its attached issuer press release are one information event unless independent structure proves otherwise.
8. Preserve contradictions as separate records; do not choose the version that later proved correct.
9. Assign economic_truth_status. A filing proves what was filed, not the objective truth of every forecast, interpretation, allegation, or risk statement.
10. Derive trust_tier from all trust dimensions, never from the numeric score alone.
11. Set confidence exactly equal to trust_profile.semantic_support_score. It is semantic support only, not probability or investment conviction.
12. Choose exactly one action: accept, reject, supersede, create_candidate, no_change, taxonomy_candidate.
13. Produce one atomic JSONL claim and keep status = review_required.
14. Record model identity, prompt hash, taxonomy version, trust policy version, limitations, and every evidence ID used.

Special rules:
- A management estimate can have semantic_support_score 0.97 and still be trust_tier C with economic_truth_status = not_independently_assessed.
- A legal allegation is attributed_only unless eligible procedural evidence establishes a decision/order.
- A structured XBRL/table number may be Tier A as a value reported for a concept/context, but a causal explanation attached to it is a separate management_interpretation claim.
- A later actual result never upgrades the earlier estimate at the earlier PIT timestamp.
- Potential events use predicate = potential_event; confidence is not event probability.
- Named relations require explicit subject, target, direction, role, and scope. Co-mention is not a relation.
- 13F is a reported quarter-end position, not trade timing, purchase price, partnership, control, or endorsement.

Do not browse the web or add external knowledge in this review batch.

Write output to:
data/sec_yfinance/reviews/<RUN_ID>/<BATCH_ID>/records.jsonl

Validate every line against:
.agents/skills/sec-llm-semantic-review/assets/llm_review_record.schema.json

Also write:
- manifest.json
- candidate_query.sql
- candidate_query.sha256
- validation.json
- challenger_records.jsonl when required

Fail the batch rather than continue if evidence identity/time differs from the database, future evidence is present, trust_profile is incomplete, confidence differs from semantic_support_score, duplicate evidence is counted as independent, inference is hidden, economic truth is upgraded without support, a PIT/integrity failure is not Tier X, or source evidence would need mutation.
```

## Suggested role split

```text
evidence-integrity-reviewer
attribution-reviewer
inference-chain-reviewer
financial-scope-reviewer
potential-event-reviewer
relation-role-reviewer
contradiction-challenger
batch-governance-validator
```

Each reviewer receives only assigned evidence and the frozen PIT boundary. The challenger receives proposed records plus the same eligible evidence, never later outcomes.

## First controlled trust batches

```text
MU:
  HBM4 sample delivery as issuer-attested occurred sampling
  reject inference from sampling to volume production

AMD:
  MI308 recorded charge: structured/reported amount versus unsupported lost-revenue interpretation
  future China sales: high semantic support but Tier C conditional potential
  TSMC relation: source-side issuer claim, role/direction/product-scope trust separated

AVGO:
  AI Revenue PSU plan adoption versus future target achievement
  anonymous customer concentration without identity guessing

NVDA:
  H20 estimate and later actual as two valid historical knowledge states
  supply-chain role decomposition without counting co-mentions as corroboration

GOOGL:
  court decision/remedy procedural trust versus allegation truth and future financial effect

META:
  Llama strategy as management interpretation without monetization or causal inference

AMZN:
  13F identity normalization only; no commercial-relationship inference
```

## Mandatory challenger routing

Require a second reviewer when:

- inference_depth is 2 or 3;
- a named supplier, customer, foundry, government, or competitor is involved;
- economic_truth_status is upgraded beyond issuer_attested without structured corroboration;
- contradiction_state is not none;
- potential becomes occurred or resolves a prior record;
- actual/guidance, GAAP basis, segment, period, unit, or scale changes;
- trust tier is C or D for a material graph relation;
- taxonomy affects more than one issuer.

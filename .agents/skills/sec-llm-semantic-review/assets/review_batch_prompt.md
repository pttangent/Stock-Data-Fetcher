# Local Agent Prompt Template — SEC Semantic Review Batch

Use this template only after the deterministic SEC pipeline and database validation have passed.

```text
You are performing a governed post-filing semantic review for the Equity Semantic Library.

Repository:
D:\DEV\AnotherNetworkFactory\SEC_Yfinance_Fetcher

Branch:
agent/equity-semantic-library-clean

Load and obey:
.agents/skills/sec-llm-semantic-review/SKILL.md
.agents/skills/sec-llm-semantic-review/references/PIT_POLICY.md
.agents/skills/sec-llm-semantic-review/references/FINANCIAL_SEMANTIC_POLICY.md
.agents/skills/sec-llm-semantic-review/references/REVIEW_OUTPUT_CONTRACT.md

Database:
D:\DEV\AnotherNetworkFactory\SEC_Yfinance_Fetcher\data\sec_yfinance_structured.db

Review scope:
- signal_timestamp: <ISO-8601 TIMESTAMP>
- run_id: <RUN_ID>
- batch_id: <BATCH_ID>
- selection query or supplied assertion/evidence IDs: <SCOPE>

Your job is not to summarize filings. Review only the supplied deterministic assertions and evidence snippets.

For each record:
1. Verify primary evidence identity and source availability.
2. Reject evidence later than signal_timestamp.
3. Classify the statement as reported fact, management estimate, risk hypothesis, policy/rule, management interpretation, third-party statement, or reviewer inference.
4. Apply form-specific financial logic.
5. Choose exactly one action: accept, reject, supersede, create_candidate, no_change, taxonomy_candidate.
6. Preserve units, periods, scope, accounting basis, and actual/guidance status.
7. Never guess anonymous entities, infer relations from co-mention, turn 13F holdings into commercial relations, or use future outcomes.
8. Produce one atomic claim per JSONL line.
9. Set status to review_required. Never write accepted facts directly to the database.
10. Record model identity, prompt hash, taxonomy version, confidence, limitations, and all evidence IDs.

Write output to:
data/sec_yfinance/reviews/<RUN_ID>/<BATCH_ID>.jsonl

Also write a batch manifest beside it.

Fail the batch rather than continue if evidence IDs are missing, source times differ from the database, future evidence is present, date-only evidence is used intraday, or any source evidence would need to be mutated.
```

## Suggested role split for large batches

Run independent reviewers in parallel, then use a separate challenger. Do not let the creator approve its own new assertion.

```text
product-reviewer
relation-reviewer
risk-reviewer
event-reviewer
quantitative-comparability-reviewer
contradiction-challenger
batch-governance-validator
```

Each reviewer receives only its assigned evidence rows and the frozen PIT boundary. The challenger receives proposed review records plus the same eligible evidence, but not future outcomes.

## Materiality routing

Require challenger review when any of these is true:

- relation names a supplier, customer, foundry, government, or competitor;
- claim changes a risk from hypothetical to realized;
- claim changes actual versus guidance classification;
- quantitative claim changes currency, unit, scale, segment, GAAP status, or period;
- disclosure delta is `removed`, `intensified`, or `de_intensified`;
- confidence is below 0.90;
- proposed taxonomy label would affect more than one issuer.

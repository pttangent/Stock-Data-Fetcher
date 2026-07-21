# Local agent instruction — full SEC/Yfinance pipeline

## Working directory and branch

Work only in:

```text
D:\DEV\AnotherNetworkFactory\SEC_Yfinance_Fetcher
```

Use branch:

```text
agent/sec-llm-semantic-review-potential
```

This branch is rebuilt from:

```text
300026e8e2571e4b03dabf9dd172d4b65b7fab74
Raise batch filing cap from 100 to 200
```

Do not edit, rewrite, or move:

```text
D:\DEV\AnotherNetworkFactory\RAW_DATA\metadata\symbol_metadata.parquet
```

The parquet file is read-only scheduling input. The pipeline writes to its own data directory and database.

## Setup

```powershell
cd D:\DEV\AnotherNetworkFactory

git clone -b agent/sec-llm-semantic-review-potential `
  https://github.com/pttangent/Stock-Data-Fetcher.git `
  SEC_Yfinance_Fetcher

cd .\SEC_Yfinance_Fetcher
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,parquet]"

Copy-Item .\config\sec_pipeline.example.json .\config\sec_pipeline.local.json
```

Verify paths in `sec_pipeline.local.json`:

```text
db_path = D:/DEV/AnotherNetworkFactory/SEC_Yfinance_Fetcher/data/sec_yfinance_structured.db
data_dir = D:/DEV/AnotherNetworkFactory/SEC_Yfinance_Fetcher/data/sec_yfinance
symbol_metadata_path = D:/DEV/AnotherNetworkFactory/RAW_DATA/metadata/symbol_metadata.parquet
```

Set a real SEC contact identity:

```powershell
$env:SEC_IDENTITY = "Stock-Data-Fetcher YOUR_REAL_EMAIL@example.com"
```

## Mandatory preflight

```powershell
pytest
python -m compileall -q .\src
esl-sec --config .\config\sec_pipeline.local.json init
```

Run the known MU archive validation first when available:

```powershell
esl-sec --config .\config\sec_pipeline.local.json import-archive `
  "D:\PATH\TO\ticker=MU.zip"

esl-sec --config .\config\sec_pipeline.local.json validate `
  --output .\reports\mu-archive-validation.json
```

Expected governance conditions:

```text
ownership_forms = 0
missing_available_at = 0
missing_evidence_time = 0
orphan_assertions = 0
sha_mismatch_issues = 0
quick_check = ok
```

## Full production run

Start the market-cap-prioritized pipeline:

```powershell
esl-sec --config .\config\sec_pipeline.local.json run 2>&1 `
  | Tee-Object -FilePath .\reports\full-pipeline.log
```

Record the persistent `RUN_ID` in:

```text
reports/RUN_ID.txt
```

Do not launch a second process against the same database. Concurrency is already internal: SEC download workers share one global rate gate; form-specific parse and deterministic semantic workers run independently.

Monitor:

```powershell
esl-sec --config .\config\sec_pipeline.local.json status <RUN_ID>
```

Resume:

```powershell
esl-sec --config .\config\sec_pipeline.local.json resume <RUN_ID>
```

Final deterministic validation:

```powershell
esl-sec --config .\config\sec_pipeline.local.json validate `
  --output .\reports\full-pipeline-validation.json
```

## Post-pipeline LLM trust-semantic review

The LLM stage is optional and begins only after deterministic validation passes.

Read:

```text
LOCAL_AGENT_SEC_LLM_REVIEW.md
.agents/skills/sec-llm-semantic-review/SKILL.md
.agents/skills/sec-llm-semantic-review/references/TRUST_SEMANTICS_POLICY.md
.agents/skills/sec-llm-semantic-review/references/REVIEW_OUTPUT_CONTRACT.md
```

The LLM reviews only selected assertions/evidence. It does not reparse raw filings or generate generic issuer summaries.

### Three separate trust questions

Every reviewed claim must distinguish:

```text
Evidence trust:
Is the source authentic, hash-verified, traceable, and PIT-eligible?

Semantic trust:
Does the source support this exact normalized claim?

Economic truth:
Does the project independently know the underlying economic statement is true?
```

A filed forecast may have strong semantic support while economic truth remains unassessed. A legal allegation may be trustworthy as an attributed allegation but not as a proven fact.

### Mandatory trust profile

Each JSONL record must include:

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

Compatibility rule:

```text
confidence == trust_profile.semantic_support_score
```

Confidence is not event probability, management-truth probability, investment conviction, materiality, expected return, or source prestige.

### Candidate selection

Use:

```text
.agents/skills/sec-llm-semantic-review/assets/select_trust_review_candidates.sql
```

Only review records selected for attribution ambiguity, inference audit, potential-event classification, relation-role refinement, contradiction review, scope comparability, or false-positive correction.

### Output

Write append-only records to:

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

Validate against:

```text
.agents/skills/sec-llm-semantic-review/assets/llm_review_record.schema.json
```

The LLM may recommend:

```text
accept
reject
supersede
create_candidate
no_change
taxonomy_candidate
```

It may not emit an accepted database status. Every new/corrected record remains `review_required` pending promotion.

## Non-negotiable controls

- Never include Forms 3, 4, 5, or 144 unless explicitly authorized.
- Process symbols by descending market cap, using rank only as fallback.
- Preserve accession, source URL, SHA-256, acceptance time, availability time, and local observation time.
- Do not infer named relations from co-mention.
- Do not guess anonymous customer/supplier identities.
- Do not turn 13F holdings into supplier, customer, partnership, control, endorsement, or trade-timing claims.
- Do not let yfinance overwrite SEC CIK or legal identity.
- Do not rewrite source evidence or historical assertions after LLM review.
- Do not count repeated wording or an 8-K plus its issuer exhibit as independent corroboration.
- Do not use later filings, prices, returns, or outcomes to upgrade earlier trust.
- PIT or evidence-integrity failure must route to `trust_tier = X`.
- Stop and report SHA mismatch, missing availability, database-integrity failure, incomplete trust profile, hidden inference, or unsupported economic-truth upgrade.

# Local agent instruction — full SEC/Yfinance pipeline

Work only in:

```text
D:\DEV\AnotherNetworkFactory\SEC_Yfinance_Fetcher
```

Use branch:

```text
agent/equity-semantic-library-clean
```

Do not edit, rewrite or move:

```text
D:\DEV\AnotherNetworkFactory\RAW_DATA\metadata\symbol_metadata.parquet
```

The parquet file is a read-only scheduling source. The pipeline must write to its separate database and data directory configured in `config/sec_pipeline.local.json`.

## Setup

```powershell
cd D:\DEV\AnotherNetworkFactory

git clone -b agent/equity-semantic-library-clean `
  https://github.com/pttangent/Stock-Data-Fetcher.git `
  SEC_Yfinance_Fetcher

cd .\SEC_Yfinance_Fetcher
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,parquet]"

Copy-Item .\config\sec_pipeline.example.json .\config\sec_pipeline.local.json
```

Verify these paths in `sec_pipeline.local.json`:

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

Run the known MU archive validation first when the ZIP is available:

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

Start the complete market-cap-prioritized pipeline:

```powershell
esl-sec --config .\config\sec_pipeline.local.json run 2>&1 `
  | Tee-Object -FilePath .\reports\full-pipeline.log
```

The command prints the persistent `RUN_ID`. Record it in `reports/RUN_ID.txt`.

Do not launch a second pipeline process against the same database. Concurrency is already internal: SEC download workers share one rate gate, while form-specific parse and semantic workers run independently.

Monitor:

```powershell
esl-sec --config .\config\sec_pipeline.local.json status <RUN_ID>
```

Resume after reboot or interruption:

```powershell
esl-sec --config .\config\sec_pipeline.local.json resume <RUN_ID>
```

Final validation:

```powershell
esl-sec --config .\config\sec_pipeline.local.json validate `
  --output .\reports\full-pipeline-validation.json
```

## Non-negotiable controls

- Never include Forms 3, 4, 5 or 144 unless the user explicitly changes policy.
- Process symbols in descending `market_cap`; use `rank` only as fallback.
- Preserve SEC accession, source URL, SHA-256, acceptance time and local observation time.
- Do not infer a named supplier/customer/competitor from loose co-occurrence. Only accepted strict issuer-first-person rules or structured 13F holdings may enter `company_relation` automatically.
- Do not allow yfinance to overwrite SEC CIK or legal identity.
- Do not delete or rewrite source evidence after LLM review. Corrections must supersede assertions while retaining `evidence_id` and original PIT timestamps.
- Stop and report if `pipeline_issue` contains SHA mismatch, missing availability time, or database integrity failures.

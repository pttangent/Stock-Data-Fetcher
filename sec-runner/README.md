# SEC pipeline runner

This replaces the old sequential ticker wrapper with the persistent multi-worker DAG in the clean Python repository.

The source branch's controls were retained and generalized:

- market-cap-descending universe order;
- free-space stop threshold;
- resumable state;
- SEC identity and request pacing;
- evidence hashes;
- Windows-friendly logs.

The important change is that the wrapper no longer launches one ticker at a time. `esl-sec` owns concurrency internally. Download workers share one SEC rate gate while form-specific parser and semantic workers consume completed accessions immediately.

```powershell
$env:SEC_IDENTITY = "Stock-Data-Fetcher your-real-email@example.com"

powershell -ExecutionPolicy Bypass -File .\sec-runner\run-sec-pipeline.ps1 `
  -Config .\config\sec_pipeline.local.json
```

Resume an interrupted persistent DAG:

```powershell
powershell -ExecutionPolicy Bypass -File .\sec-runner\run-sec-pipeline.ps1 `
  -Config .\config\sec_pipeline.local.json `
  -RunId "sec-run:..."
```

Do not run two wrappers against the same DB. The lock file is `reports/sec-pipeline.lock`.

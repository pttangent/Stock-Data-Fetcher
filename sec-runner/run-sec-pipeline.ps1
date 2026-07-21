param(
  [string]$Config = ".\config\sec_pipeline.local.json",
  [string]$RunId = "",
  [int]$Limit = 0
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

if (-not $env:SEC_IDENTITY -and -not $env:SEC_USER_AGENT) {
  throw "Set SEC_IDENTITY or SEC_USER_AGENT with a real contact email before starting the online pipeline."
}

$Reports = Join-Path $Repo "reports"
New-Item -ItemType Directory -Force -Path $Reports | Out-Null
$Lock = Join-Path $Reports "sec-pipeline.lock"
if (Test-Path $Lock) {
  $existing = Get-Content $Lock -ErrorAction SilentlyContinue
  throw "Pipeline lock already exists: $Lock ($existing). Confirm no process is active before removing it."
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$log = Join-Path $Reports "sec-pipeline-$stamp.log"
Set-Content -Path $Lock -Value "PID=$PID STARTED=$(Get-Date -Format o) CONFIG=$Config"

try {
  if ($RunId) {
    & esl-sec --config $Config resume $RunId 2>&1 | Tee-Object -FilePath $log
  } else {
    $args = @("--config", $Config, "run")
    if ($Limit -gt 0) { $args += @("--limit", "$Limit") }
    & esl-sec @args 2>&1 | Tee-Object -FilePath $log
  }
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
  Remove-Item $Lock -Force -ErrorAction SilentlyContinue
}

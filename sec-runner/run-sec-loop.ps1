# Detached SEC backfill loop
# Runs the Python wrapper in batches and restarts automatically.
#
# Required: set SEC_USER_AGENT environment variable before running, e.g.:
#   $env:SEC_USER_AGENT = "Stock-Data-Fetcher <your-real-email@example.com>"

$OutputDir = "D:\SEC_WAREHOUSE"
$RepoDir = "D:\DEV\USTOCK\SEC\Stock-Data-Fetcher"
$ScriptDir = "D:\DEV\USTOCK\SEC"

if (-not $env:SEC_USER_AGENT) {
    Write-Error "SEC_USER_AGENT environment variable is required"
    exit 1
}

while ($true) {
    $free = (Get-Volume -DriveLetter D).SizeRemaining / 1GB
    if ($free -le 5.5) {
        Add-Content -Path "$ScriptDir\backfill-progress.log" -Value "[$(Get-Date -Format o)] LOOP: D: free space $free GiB <= 5.5 GiB, stopping loop"
        break
    }

    Add-Content -Path "$ScriptDir\backfill-progress.log" -Value "[$(Get-Date -Format o)] LOOP: starting batch, D: free = $([math]::Round($free,2)) GiB"

    $proc = Start-Process -FilePath "python" -ArgumentList "$RepoDir\sec-runner\run-sec-backfill.py", "--max-tickers", "2" -WorkingDirectory $RepoDir -WindowStyle Hidden -PassThru -RedirectStandardOutput "$ScriptDir\backfill-stdout.log" -RedirectStandardError "$ScriptDir\backfill-stderr.log"
    $proc.WaitForExit()

    Add-Content -Path "$ScriptDir\backfill-progress.log" -Value "[$(Get-Date -Format o)] LOOP: batch exited with code $($proc.ExitCode), restarting in 30s"
    Start-Sleep -Seconds 30
}

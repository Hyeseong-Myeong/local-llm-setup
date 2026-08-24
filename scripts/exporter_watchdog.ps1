# Restarts local_exporter.py / Alloy on the dev PC if either stops responding.
# Registered via scripts/manage_tasks.ps1 as LocalLLM-MonitoringWatchdog (every 10 min).
# Push architecture means Prometheus can't report `up=0` when these die
# (Docs/plg_monitoring_design.md 6-1) - this is the auto-recovery side; the
# "No Data" alert rule (9-1) is the detection backstop for cases this can't fix.

$RepoRoot = "C:\local_LLM"

function Test-Endpoint($Url) {
    try {
        $resp = Invoke-WebRequest -Uri $Url -TimeoutSec 5 -UseBasicParsing
        return $resp.StatusCode -eq 200
    } catch {
        return $false
    }
}

if (-not (Test-Endpoint "http://127.0.0.1:13092/metrics")) {
    Write-Output "$(Get-Date -Format o) local_exporter not responding - restarting"
    Start-Process -FilePath "$RepoRoot\venv\Scripts\pythonw.exe" `
        -ArgumentList "exporter\local_exporter.py" -WorkingDirectory $RepoRoot
}

if (-not (Test-Endpoint "http://127.0.0.1:12345/-/ready")) {
    Write-Output "$(Get-Date -Format o) alloy not responding - restarting"
    Start-Process -FilePath "$RepoRoot\monitoring\devpc\start-alloy.bat" `
        -WorkingDirectory "$RepoRoot\monitoring\devpc" -WindowStyle Hidden
}

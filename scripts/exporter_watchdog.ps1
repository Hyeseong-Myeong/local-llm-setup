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

function Stop-Stale($Filter, $Label) {
    # An unresponsive process must be cleared before a replacement is started.
    # Measured incident: this script used to start a second local_exporter next
    # to a wedged one. Python's HTTPServer sets SO_REUSEADDR, which on Windows
    # means "may take over a port that is already in use", so both processes
    # bound 13092 and it was undefined which of them answered Alloy's scrape.
    # Worse, the port kept answering, so the watchdog could never notice the
    # duplicate it had created. local_exporter.py now refuses the second bind;
    # this clears the wedged first one so that refusal never comes up.
    $procs = @(Get-CimInstance Win32_Process -Filter $Filter -ErrorAction SilentlyContinue)
    foreach ($p in $procs) {
        Write-Output "$(Get-Date -Format o) $Label stale PID $($p.ProcessId) - terminating"
        Invoke-CimMethod -InputObject $p -MethodName Terminate -ErrorAction SilentlyContinue | Out-Null
    }
    if ($procs.Count -gt 0) { Start-Sleep -Seconds 3 }
}

if (-not (Test-Endpoint "http://127.0.0.1:13092/metrics")) {
    Write-Output "$(Get-Date -Format o) local_exporter not responding - restarting"
    # Name is pinned to python so the filter cannot match, say, a shell that
    # merely mentions the script name on its own command line.
    Stop-Stale "Name LIKE 'python%' AND CommandLine LIKE '%local_exporter.py%'" "local_exporter"
    Start-Process -FilePath "$RepoRoot\venv\Scripts\pythonw.exe" `
        -ArgumentList "exporter\local_exporter.py" -WorkingDirectory $RepoRoot
}

if (-not (Test-Endpoint "http://127.0.0.1:12345/-/ready")) {
    Write-Output "$(Get-Date -Format o) alloy not responding - restarting"
    Stop-Stale "Name = 'alloy.exe'" "alloy"
    Start-Process -FilePath "$RepoRoot\monitoring\devpc\start-alloy.bat" `
        -WorkingDirectory "$RepoRoot\monitoring\devpc" -WindowStyle Hidden
}

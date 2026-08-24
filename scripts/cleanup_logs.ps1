# Deletes log files older than the retention period.
# Covers app logs (logs/*-YYYYMMDD.log, 4-1) and Ollama logs (logs/ollama-*.log[.err], 6-4)
# with one shared policy - Docs/plg_monitoring_design.md 6-4, 9-3.
# Retention matches Loki's (30 days, section 7) so local files and Loki don't drift apart.
param([int]$Days = 30, [string]$LogDir = "C:\local_LLM\logs")

$cutoff = (Get-Date).AddDays(-$Days)
Get-ChildItem -Path $LogDir -File -Include "*-*.log", "*.log.*" -Recurse |
    Where-Object { $_.LastWriteTime -lt $cutoff } |
    ForEach-Object {
        Write-Output "delete $($_.Name) ($([math]::Round($_.Length/1MB,1))MB, $($_.LastWriteTime.ToString('yyyy-MM-dd')))"
        Remove-Item $_.FullName -Force
    }

# Deletes old log files, then enforces a total size cap on the log directory.
# Covers app logs (logs/*-YYYYMMDD.log, 4-1), Ollama logs (logs/ollama-*.log[.err],
# 6-4) and Alloy's own logs (logs/alloy-*.log[.err]) with one shared policy -
# Docs/plg_monitoring_design.md 6-4, 9-3.
#
# Retention used to be 30 days to match Loki's. It is now 7 with a hard size cap:
# these local files are only a buffer in front of Loki, which still keeps 30 days
# (section 7), and C: on the dev PC runs with under 10GB free.
param(
    [int]$Days = 7,
    [int]$MaxTotalMB = 200,
    [string]$LogDir = "C:\local_LLM\logs"
)

# Anything written in the last day is assumed to still be open by its process -
# Ollama and Alloy each keep one file open for their whole run, and Windows
# refuses to delete an open file. Skipping them keeps the output free of noise.
$activeCutoff = (Get-Date).AddDays(-1)
$patterns = @("*-*.log", "*.log.*")

$script:freedBytes = 0

function Remove-LogFile($file, $reason) {
    try {
        Remove-Item $file.FullName -Force -ErrorAction Stop
        $script:freedBytes += $file.Length
        Write-Output ("delete {0} ({1}MB, {2}, {3})" -f $file.Name,
            [math]::Round($file.Length / 1MB, 1), $file.LastWriteTime.ToString('yyyy-MM-dd'), $reason)
    } catch {
        Write-Output "skip   $($file.Name) - in use"
    }
}

$candidates = @(Get-ChildItem -Path $LogDir -File -Include $patterns -Recurse |
    Where-Object { $_.LastWriteTime -lt $activeCutoff })

# 1) age based
$cutoff = (Get-Date).AddDays(-$Days)
foreach ($f in ($candidates | Where-Object { $_.LastWriteTime -lt $cutoff })) {
    Remove-LogFile $f "older than $Days days"
}

# 2) size cap on whatever survived, oldest first
$remaining = @(Get-ChildItem -Path $LogDir -File -Include $patterns -Recurse)
$totalBytes = ($remaining | Measure-Object Length -Sum).Sum
Write-Output ("logs dir: {0}MB (cap {1}MB)" -f [math]::Round($totalBytes / 1MB, 1), $MaxTotalMB)

$over = $totalBytes - ($MaxTotalMB * 1MB)
if ($over -gt 0) {
    $script:freedBytes = 0
    foreach ($f in ($remaining | Where-Object { $_.LastWriteTime -lt $activeCutoff } | Sort-Object LastWriteTime)) {
        if ($script:freedBytes -ge $over) { break }
        Remove-LogFile $f "over size cap"
    }
    Write-Output ("freed {0}MB to meet the cap" -f [math]::Round($script:freedBytes / 1MB, 1))
}

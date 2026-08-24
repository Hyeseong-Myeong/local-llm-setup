# Manages this project's Windows Scheduled Tasks from one place instead of
# registering/unregistering by hand in the GUI (Docs/plg_monitoring_design.md 9-4).
# Must run in an elevated (Administrator) PowerShell - task registration needs it.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\manage_tasks.ps1 -Action install
#   powershell -ExecutionPolicy Bypass -File scripts\manage_tasks.ps1 -Action status
#   powershell -ExecutionPolicy Bypass -File scripts\manage_tasks.ps1 -Action remove

param([ValidateSet("install", "remove", "status")][string]$Action = "status")

$Tasks = @(
    @{ Name = "LocalLLM-MonitoringWatchdog"
       Script = "C:\local_LLM\scripts\exporter_watchdog.ps1"
       Trigger = "Repeat"; IntervalMinutes = 10 }
    @{ Name = "LocalLLM-CleanupLogs"
       Script = "C:\local_LLM\scripts\cleanup_logs.ps1"
       Trigger = "Daily"; At = "04:00" }
)

function New-TriggerFor($t) {
    if ($t.Trigger -eq "Daily") {
        return New-ScheduledTaskTrigger -Daily -At $t.At
    }
    # "Repeat": once-at-now trigger with a repetition interval layered on top.
    # [TimeSpan]::MaxValue overflows the task XML duration format, so a large
    # bounded duration (10 years) stands in for "indefinitely."
    return New-ScheduledTaskTrigger -Once -At (Get-Date) `
        -RepetitionInterval (New-TimeSpan -Minutes $t.IntervalMinutes) `
        -RepetitionDuration (New-TimeSpan -Days 3650)
}

function Install-Tasks {
    foreach ($t in $Tasks) {
        if (Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false
        }
        $action = New-ScheduledTaskAction -Execute "powershell.exe" `
            -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$($t.Script)`""
        $trigger = New-TriggerFor $t
        # SYSTEM + ServiceAccount: no stored password needed, and it runs without
        # anyone logged in - the whole point of using a scheduled task here (9-4).
        $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
        try {
            Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger -Principal $principal -ErrorAction Stop | Out-Null
            Write-Output "installed: $($t.Name)"
        } catch {
            Write-Output "FAILED to install $($t.Name): $($_.Exception.Message)"
        }
    }
}

function Remove-Tasks {
    foreach ($t in $Tasks) {
        if (Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false
            Write-Output "removed: $($t.Name)"
        } else {
            Write-Output "not registered: $($t.Name)"
        }
    }
}

function Show-Status {
    # A SYSTEM-owned task can return "access denied" when queried as a normal
    # user - Get-ScheduledTask with -ErrorAction SilentlyContinue swallows that
    # error too and just returns $null, so "genuinely not registered" and
    # "couldn't check, no permission" must be told apart explicitly.
    foreach ($t in $Tasks) {
        $err = $null
        $task = Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue -ErrorVariable err
        if (-not $task) {
            if ($err) {
                Write-Output "$($t.Name): UNKNOWN (query failed - recheck from an elevated prompt: $($err[0].Exception.Message))"
            } else {
                Write-Output "$($t.Name): NOT REGISTERED"
            }
            continue
        }
        $info = Get-ScheduledTaskInfo -TaskName $t.Name
        Write-Output "$($t.Name): $($task.State), last run $($info.LastRunTime) (result $($info.LastTaskResult)), next run $($info.NextRunTime)"
    }
}

switch ($Action) {
    "install" { Install-Tasks }
    "remove"  { Remove-Tasks }
    "status"  { Show-Status }
}

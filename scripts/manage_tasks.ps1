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
    # Nightly vault cross-check (Docs/local_model_feature_proposals.md 4).
    #
    # RunAs = "User", not SYSTEM, unlike the two tasks above. Reasons:
    #   - The reranker loads its model from the *user's* HuggingFace cache
    #     (~/.cache/huggingface, ~2.2GB). SYSTEM has a different profile and no
    #     HOME, so it would re-download or fail outright.
    #   - It needs the venv and the repo .env the same way an interactive run does.
    # LogonType Interactive means "only runs while the user is logged on", which
    # is true on this desktop; sleep suspends the session but does not end it.
    #
    # WakeToRun + StartWhenAvailable are both set (see New-SettingsFor):
    #   - WakeToRun covers S3 sleep, best effort - it also needs the power plan's
    #     "Allow wake timers" enabled (verify: powercfg /query, and BIOS).
    #   - StartWhenAvailable is the safety net for hibernate/shutdown, where wake
    #     timers generally do not fire. The batch itself then refuses to run
    #     outside 04-09h (ALLOWED_HOUR_RANGE) so a late catch-up cannot take the
    #     embedding model down in the middle of a working day.
    @{ Name = "LocalLLM-NightlyBatch"
       Script = "C:\local_LLM\src\agent\nightly_batch.py"
       Interpreter = "C:\local_LLM\venv\Scripts\python.exe"
       Trigger = "Daily"; At = "05:00"
       RunAs = "User"; WakeToRun = $true }
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

function New-ActionFor($t) {
    # A task with an explicit Interpreter runs that binary directly (python.exe
    # for the nightly batch); everything else is a .ps1 run through powershell.
    if ($t.Interpreter) {
        return New-ScheduledTaskAction -Execute $t.Interpreter `
            -Argument "`"$($t.Script)`"" -WorkingDirectory "C:\local_LLM"
    }
    return New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$($t.Script)`""
}

function New-PrincipalFor($t) {
    if ($t.RunAs -eq "User") {
        # Interactive: runs only while this user is logged on, under their
        # profile - needed for the HuggingFace cache (see the task table above).
        # No stored password required, unlike "run whether logged on or not".
        return New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
    }
    # SYSTEM + ServiceAccount: no stored password needed, and it runs without
    # anyone logged in - the whole point of using a scheduled task here (9-4).
    return New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
}

function New-SettingsFor($t) {
    # StartWhenAvailable on every task: if the box was off at the scheduled
    # time, run the task once it is back rather than skipping the day silently.
    if ($t.WakeToRun) {
        return New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun
    }
    return New-ScheduledTaskSettingsSet -StartWhenAvailable
}

function Install-Tasks {
    foreach ($t in $Tasks) {
        if (Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false
        }
        $action = New-ActionFor $t
        $trigger = New-TriggerFor $t
        $principal = New-PrincipalFor $t
        $settings = New-SettingsFor $t
        try {
            Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger `
                -Principal $principal -Settings $settings -ErrorAction Stop | Out-Null
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

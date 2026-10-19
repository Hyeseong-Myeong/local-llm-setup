@echo off
echo =========================================
echo       AI Server Shutdown Script
echo =========================================
echo.

:: Capture the process list BEFORE terminating anything.
:: Why: troubleshooting.md TODO - wiki_agent/discord_bot once showed 4 processes
:: each instead of the normal 2, and it never reproduced. Without a snapshot taken
:: at shutdown time there is nothing to diagnose when it happens again.
:: ASCII only in this file - cmd.exe misparses UTF-8 .bat on this machine.
echo 0. Capturing process snapshot for diagnostics...
powershell -NoProfile -Command "$stamp = Get-Date -Format yyyyMMdd_HHmmss; $out = Join-Path '%~dp0logs' ('shutdown_procs_' + $stamp + '.log'); New-Item -ItemType Directory -Force -Path (Join-Path '%~dp0' 'logs') | Out-Null; Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -or $_.Name -eq 'ollama.exe' -or $_.Name -eq 'llama-server.exe' -or $_.Name -eq 'alloy.exe' } | Select-Object ProcessId, ParentProcessId, Name, CommandLine | Sort-Object Name, ParentProcessId | Format-Table -AutoSize | Out-File -FilePath $out -Encoding utf8; Write-Host ('  -[OK] Snapshot: ' + $out)"

echo.
echo 1. Terminating discord_bot.py...
powershell -NoProfile -Command "$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*discord_bot.py*' }; if ($procs) { $procs | ForEach-Object { Invoke-CimMethod -InputObject $_ -MethodName Terminate -ErrorAction SilentlyContinue | Out-Null; Write-Host '  -[OK] Terminated PID:' $_.ProcessId } } else { Write-Host '  -[SKIP] discord_bot.py is not running.' }"

echo.
echo 2. Terminating wiki_agent.py...
powershell -NoProfile -Command "$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*wiki_agent.py*' }; if ($procs) { $procs | ForEach-Object { Invoke-CimMethod -InputObject $_ -MethodName Terminate -ErrorAction SilentlyContinue | Out-Null; Write-Host '  -[OK] Terminated PID:' $_.ProcessId } } else { Write-Host '  -[SKIP] wiki_agent.py is not running.' }"

echo.
echo 3. Terminating fastapi_wiki_server.py...
powershell -NoProfile -Command "$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*fastapi_wiki_server.py*' }; if ($procs) { $procs | ForEach-Object { Invoke-CimMethod -InputObject $_ -MethodName Terminate -ErrorAction SilentlyContinue | Out-Null; Write-Host '  -[OK] Terminated PID:' $_.ProcessId } } else { Write-Host '  -[SKIP] fastapi_wiki_server.py is not running.' }"

echo.
echo 4. Stopping Bifrost Docker Containers...
cd bifrost && docker-compose stop && cd ..

echo.
echo 5. Terminating local_exporter.py...
powershell -NoProfile -Command "$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*local_exporter.py*' }; if ($procs) { $procs | ForEach-Object { Invoke-CimMethod -InputObject $_ -MethodName Terminate -ErrorAction SilentlyContinue | Out-Null; Write-Host '  -[OK] Terminated PID:' $_.ProcessId } } else { Write-Host '  -[SKIP] local_exporter.py is not running.' }"

echo.
echo 6. Terminating Alloy...
powershell -NoProfile -Command "$procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'alloy.exe' -or $_.CommandLine -like '*GrafanaAlloy*' }; if ($procs) { $procs | ForEach-Object { Invoke-CimMethod -InputObject $_ -MethodName Terminate -ErrorAction SilentlyContinue | Out-Null; Write-Host '  -[OK] Terminated PID:' $_.ProcessId } } else { Write-Host '  -[SKIP] Alloy is not running.' }"

echo.
echo All related AI software has been successfully shut down.

@echo off
echo =========================================
echo       AI Server Shutdown Script
echo =========================================
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
echo All related AI software has been successfully shut down.

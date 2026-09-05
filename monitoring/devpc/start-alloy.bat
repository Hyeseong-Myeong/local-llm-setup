@echo off
:: Dev PC Alloy startup - build step 4 (Docs/plg_monitoring_design.md 6-1).
:: Called from ai-server-start.bat alongside the other agents.
:: Korean text avoided here - cmd.exe misparses UTF-8 .bat files on this machine.

set "SCRIPT_DIR=%~dp0"
set "LOGDIR=C:\local_LLM\logs"

if not exist "%SCRIPT_DIR%.env" (
    echo [Alloy] %SCRIPT_DIR%.env not found. Copy .env.example and fill in NAS_TAILNET_IP.
    exit /b 1
)

for /f "usebackq eol=# tokens=1,2 delims==" %%A in ("%SCRIPT_DIR%.env") do (
    set "%%A=%%B"
)

if "%NAS_TAILNET_IP%"=="" (
    echo [Alloy] NAS_TAILNET_IP is empty.
    exit /b 1
)

:: Per-launch log file name. Alloy's own stderr used to go nowhere, so a
:: remote-write outage left nothing to read afterwards. The stamp is needed for
:: the same reason as the Ollama launch in ai-server-start.bat: a file reopened
:: under the same name is not seen as new on Windows (alloy#2292).
:: On purpose these files are NOT matched by config.alloy - shipping Alloy's own
:: error log through Alloy would feed a push failure back into itself.
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set LDT=%%I
set STAMP=%LDT:~0,8%-%LDT:~8,4%

:: Hidden background launch - a plain foreground call here keeps the wrapping
:: cmd window open forever (alloy.exe never exits on its own), so restart.bat
:: never closes it. Mirrors the Ollama launch in ai-server-start.bat.
powershell -WindowStyle Hidden -Command "Start-Process -WindowStyle Hidden -FilePath 'C:\GrafanaAlloy\alloy.exe' -ArgumentList 'run','--server.http.listen-addr=127.0.0.1:12345','--storage.path=C:\GrafanaAlloy\data','%SCRIPT_DIR%config.alloy' -RedirectStandardOutput '%LOGDIR%\alloy-%STAMP%.log' -RedirectStandardError '%LOGDIR%\alloy-%STAMP%.err.log'"

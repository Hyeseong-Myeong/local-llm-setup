@echo off
:: Dev PC Alloy startup - build step 4 (Docs/plg_monitoring_design.md 6-1).
:: Called from ai-server-start.bat alongside the other agents.
:: Korean text avoided here - cmd.exe misparses UTF-8 .bat files on this machine.

set "SCRIPT_DIR=%~dp0"

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

"C:\GrafanaAlloy\alloy.exe" run --server.http.listen-addr=127.0.0.1:12345 --storage.path=C:\GrafanaAlloy\data "%SCRIPT_DIR%config.alloy"

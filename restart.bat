@echo off
echo =========================================
echo       AI Server Restart Script
echo =========================================
echo.

echo [Step 1] Shutting down existing services...
call shutdown.bat

echo.
echo [Step 2] Starting services...
call "C:\Users\mhsjs\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\ai-server-start.bat"

@echo off
cd /d "%~dp0"
title Faiyke assistant server
start "" /b cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8080"
python -m rag.server
echo.
echo Server stopped.
pause

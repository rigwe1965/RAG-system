@echo off
cd /d "%~dp0"
title Project hub server
start "" /b cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8090/hub"
python -m rag.hub serve
echo.
echo Server stopped.
pause

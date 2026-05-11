@echo off
title Clash Dynasty TCG
echo.
echo  ========================================
echo    CLASH DYNASTY TCG - Starting...
echo  ========================================
echo.

cd /d "%~dp0"

:: Clear Python cache
if exist __pycache__ rmdir /s /q __pycache__
echo  Cache cleared. Loading latest server code...
echo.

:: Open browser after 2 seconds
start /b cmd /c "timeout /t 2 >nul && start http://localhost:8080"

echo  Server starting at http://localhost:8080
echo  Press Ctrl+C to stop.
echo.

:: Use the exact Python path that works on this machine
"C:\Users\Jeffrey\AppData\Local\Programs\Python\Python313\python.exe" server.py

pause

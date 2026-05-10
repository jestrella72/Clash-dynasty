@echo off
title Clash Dynasty TCG
echo.
echo  ========================================
echo    CLASH DYNASTY TCG - Starting...
echo  ========================================
echo.

:: Always clear Python bytecode cache so latest server.py changes are loaded
if exist __pycache__ rmdir /s /q __pycache__
echo  Cache cleared. Loading latest server code...
echo.
echo  Opening game in your browser...
echo  Press Ctrl+C in this window to stop.
echo.

:: Open browser after 2 seconds
start /b cmd /c "timeout /t 2 >nul && start http://localhost:8080"

:: Start the server
python server.py

pause

@echo off
setlocal
cd /d "%~dp0"

python --version >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found.
  echo Please install Python first.
  pause
  exit /b 1
)

python ".\app.py"

endlocal

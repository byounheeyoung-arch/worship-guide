@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m worship_guide
) else (
  python -m worship_guide
)
if errorlevel 1 pause

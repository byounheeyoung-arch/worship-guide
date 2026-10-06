@echo off
set PY=C:\wge-venv\Scripts\python.exe
if exist "%PY%" (
  "%PY%" -m worship_guide.editor
) else (
  python -m worship_guide.editor
)
pause

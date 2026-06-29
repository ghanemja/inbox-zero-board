@echo off
REM Inbox Zero — local desktop Outlook ingest + UI export (Windows, no Azure).
REM Point Windows Task Scheduler at this file to run it on a schedule.

REM cd to the backend folder (this script lives in backend\scripts)
cd /d "%~dp0\.."

REM activate the venv if present (created with: python -m venv .venv)
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

REM pull from the signed-in desktop Outlook, classify locally, then export for the UI
python scripts\run_ingest.py --source outlook-local --limit 200
python scripts\export_ui.py --out "..\prototype\data.json"

echo Done. Open the UI (serve the prototype\ folder) to see your mail.

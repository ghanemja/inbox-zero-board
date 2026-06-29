# Run on real mail with NO Azure — desktop Outlook (Windows)

If you have the classic **Outlook desktop app** signed in on Windows, you can skip
Azure entirely. This reads mail straight from Outlook via COM (pywin32). No app
registration, no cloud token, no network egress — the most local-first option.

> Requires the **classic** Outlook desktop app (not the new "Outlook for Windows"
> store app, which lacks COM). Windows only.

## One-time setup

```bat
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt        REM installs pywin32 on Windows

REM local model for good triage (optional but recommended):
REM   install Ollama from https://ollama.com, then:
ollama pull gemma3:4b
```

No `.env` needed for this path (no Azure keys). Make sure Outlook is open and
signed in.

## Pull + classify your real inbox

```bat
REM from backend\, venv active. --me auto-detects your signed-in Outlook account.
python scripts\run_ingest.py --source outlook-local --limit 200
python scripts\export_ui.py --out ..\prototype\data.json
```

Then serve the UI and open it:

```bat
cd ..
python -m http.server 4178 --directory prototype
REM open http://localhost:4178/  -> log in -> your real mail
```

A reusable one-click script is provided: **`backend\scripts\run_local.bat`** (does
the ingest + export in one go).

## Rolling out to a pilot with years of mail

Don't Gemma-classify years of email on the first run — that's hours. Three phases:

**Phase 1 — recent window, full classification (get boards working fast).**
```bat
python scripts\run_ingest.py --source outlook-local --days 30 --limit 3000
python scripts\export_ui.py --out ..\prototype\data.json
```
Last 30 days → Today / Board / Commitments populated. Rough time: tens of minutes to
~an hour depending on machine + GPU + volume. Start at `--days 14` if you want value
sooner; widen later (it only processes the new days).

**Phase 2 — history backfill, metadata-only (years of graph depth, cheap).**
```bat
python scripts\run_ingest.py --source outlook-local --backfill --limit 50000
```
Builds the relationship graph, comm-style, commitments, and interaction history from
your whole archive **without** running Gemma per email (rules + metadata only). This is
where "years of mail" pays off — the compounding graph. Fast: minutes, not hours.

**Phase 3 — keep it running, incremental (cheap, ongoing).**
```bat
REM re-running only processes NEW mail; already-seen mail is skipped, graph never double-counts
python scripts\run_ingest.py --source outlook-local --days 7
python scripts\export_ui.py --out ..\prototype\data.json
```
Schedule this (below). Each run touches only new mail → seconds to a couple minutes.

## Schedule it (the "cron" for Windows = Task Scheduler)

Run it automatically, e.g. hourly:

```bat
schtasks /Create /SC HOURLY /TN "InboxZero" ^
  /TR "C:\path\to\emails\backend\scripts\run_local.bat"
```

- Other cadences: `/SC MINUTE /MO 30` (every 30 min), `/SC DAILY /ST 08:00`.
- Outlook must be running for the COM pull to work; "run only when user is logged on"
  is the right Task Scheduler option.
- Inspect/stop later: `schtasks /Query /TN "InboxZero"` · `schtasks /Delete /TN "InboxZero"`.
- Or use the Task Scheduler GUI: Create Basic Task → trigger (e.g. hourly) →
  action "Start a program" → browse to `run_local.bat`.

## Notes

- **Read-only.** The connector only reads the inbox; it never sends or modifies mail.
- **Bodies are plain text** already from Outlook — no HTML stripping needed.
- `inboxzero.db` and `prototype\data.json` hold your real mail — both are gitignored.
  **Never commit or push them.**
- Exchange/work accounts: addresses are resolved from Exchange DN to real SMTP
  automatically. If your org locks down COM/macros, this path may be blocked — then
  use the Azure/Graph path in [outlook-setup.md](outlook-setup.md) instead.

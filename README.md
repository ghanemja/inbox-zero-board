# Inbox Zero Board

Turn an Outlook inbox into a calm, organized workspace — not a pile of mail. Local-first:
mail is read on-device, classified by a local model, and nothing leaves the machine.

**Tabs**

- **Today** — the calm landing: what needs you now (top tasks by due date), overdue commitments, team health, one insight. A digest, not another inbox.
- **Board** — every email sorted into **To-Do** (action required), **Awareness** (cc'd/FYI, clear when seen), **Projects** (related threads auto-grouped).
- **Commitments** — who owes whom, both ways, with SLA timers; resolve / snooze / nudge.
- **Delegate** — file a ticket → it routes the implied asks to the right people with the details they need, learned from past threads.
- **Insights** — relationship graph + per-person communication style, topic share, and an opt-in, behavioral-only relationship-health view.

## Live demo

GitHub Pages serves the clickable prototype with **seed data** (no real email), entirely in the browser:
**https://ghanemja.github.io/inbox-zero-board/**

Login is a **cosmetic demo gate** (`admin` / `password`) — not real security (static site; the
value is in the page source). Do not put real data behind it.

## Repo layout

| Path | What |
|---|---|
| `prototype/` | Self-contained UI (no build, no CDN). What Pages hosts; also the local dashboard. |
| `backend/` | Local engine: Outlook → SQLite → rules + local Gemma (Ollama) → boards, profiles, commitments, graph. |
| `docs/` | [learning-logic](docs/learning-logic.md), [roadmap](docs/roadmap.md), [windows-local-setup](docs/windows-local-setup.md), [outlook-setup](docs/outlook-setup.md) |

---

## Run it on your real inbox (Windows, no Azure)

If you have the **classic Outlook desktop app** signed in, this reads your inbox directly via
COM — no app registration, no cloud token. Full guide: [docs/windows-local-setup.md](docs/windows-local-setup.md).

### One-time setup

```bat
git clone https://github.com/ghanemja/inbox-zero-board
cd inbox-zero-board\backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
ollama pull gemma3:4b          REM local model (install Ollama from https://ollama.com first)
```

### First run — recent window (fast)

```bat
REM from backend\, venv active. --me auto-detects the signed-in Outlook account.
python scripts\run_ingest.py --source outlook-local --days 30 --limit 3000
python scripts\export_ui.py --out ..\prototype\data.json
```

### Run the UI

```bat
cd ..\prototype
python -m http.server 4178
REM open http://localhost:4178/  → log in
```

The ingest+export writes `prototype\data.json`; the UI reads it. They're decoupled — the
dashboard always shows the latest export. Leave the UI server running; re-run ingest+export
(then reload the page) to refresh.

### History backfill (optional, once) — years of relationship graph, cheap

```bat
python scripts\run_ingest.py --source outlook-local --backfill --limit 50000
```
Builds the graph / comm-style / commitments from your whole archive **without** per-email
Gemma. Minutes, not hours. Run it overnight after the first demo.

### Keep it running (recurring)

Two pieces: a scheduled **data refresh**, and the **UI server** staying up.

```bat
REM data refresh — hourly. backend\scripts\run_local.bat does ingest + export.
schtasks /Create /SC HOURLY /TN "InboxZero" ^
  /TR "C:\path\to\inbox-zero-board\backend\scripts\run_local.bat"

REM UI server — start at logon so the dashboard is always available:
schtasks /Create /SC ONLOGON /TN "InboxZeroUI" ^
  /TR "cmd /c cd /d C:\path\to\inbox-zero-board\prototype && python -m http.server 4178"
```

Each scheduled run only processes **new** mail (seen mail is skipped; the graph never
double-counts), so runs stay fast. Outlook must be open when the refresh runs.

> Mac / headless / non-Windows? Use the Microsoft Graph path instead: [docs/outlook-setup.md](docs/outlook-setup.md).

---

## Privacy

Local-first by design: mail bodies stay in an on-device SQLite file (`backend/inboxzero.db`),
classification runs on a local model, every decision logs its reasoning + confidence, and
low-confidence items go to a review lane rather than being auto-acted. With the desktop-Outlook
+ local-Gemma path there is **zero email egress** (verifiable by air-gapping after the model is
pulled). `inboxzero.db` and `prototype/data.json` hold real mail and are gitignored — **never
commit or push them**; the hosted demo stays seed-only.

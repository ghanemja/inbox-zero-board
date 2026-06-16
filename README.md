# Inbox Zero Board

Turn an Outlook inbox into a task board, not a pile of mail. Every email is sorted into:

- **To-Do** — action required (the engine extracts the task, due date, and *why*)
- **Awareness** — cc'd / FYI / bulk, cleared with a checkbox
- **Projects** — related emails auto-grouped into long-running work (a conference submission, a hire, a contract)

Plus a **Delegate** tab (file a ticket → it routes the implied asks to the right people with the details they need, learned from past threads), an **Org** rollup (per-team load + health for execs), and an **Insights** relationship graph.

## Live demo

GitHub Pages serves the clickable prototype (seed data, runs entirely in the browser).
Login is a **cosmetic demo gate** — `admin` / `admin`. It is **not** real security (static site; credentials are visible in source). Do not put real data behind it.

## Repo

| Path | What |
|---|---|
| `prototype/` | Self-contained clickable UI (no build, no CDN). This is what Pages hosts. |
| `backend/` | Local-first engine: Outlook (MS Graph) → SQLite → rules + local Gemma (Ollama) → board, profiles, playbooks. Nothing leaves the machine. |
| `docs/learning-logic.md` | How email history becomes contact profiles + delegate playbooks. |

## Run the real engine locally

See [`backend/README.md`](backend/README.md). In short: `pip install -r backend/requirements.txt`, `ollama pull gemma3:4b`, register an Azure app (Mail.Read), then `python backend/scripts/run_ingest.py`. Export to the UI with `backend/scripts/export_ui.py` → drops `prototype/data.json`, which the UI loads over its demo seed.

## Privacy

The engine is local-first by design: mail bodies stay in an on-device SQLite file, classification uses a local model, every decision logs its reasoning + confidence, and low-confidence items go to a review lane instead of being auto-actioned. The hosted Pages demo contains **no real email** — only seed data.

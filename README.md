# Inbox Zero Board

Turn your inbox into a calm task board. Mail is read on your machine, sorted by a
local model, and shown in a simple dashboard. Nothing is sent to any third party.

**Live demo (fake data):** https://ghanemja.github.io/inbox-zero-board/ — login `admin` / `password`.

---

## Setup (once)

> Mac uses `python3` and `/`. Windows uses `python` and `\`.

```bash
git clone https://github.com/ghanemja/inbox-zero-board
cd inbox-zero-board/backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python3 -m pip install -r requirements.txt
```

Optional but recommended for good sorting — install [Ollama](https://ollama.com), then:
```bash
ollama pull gemma3:4b
```
(Skip it and add `--no-gemma` to the commands below for a quick first run; sorting is rougher.)

---

## Step 1 — get your email in

Pick **one** source that fits your setup. Run from the `backend/` folder with the venv active.
Replace `YOUR_EMAIL` with your address.

### A. Manual export — works everywhere, fully offline (recommended)
No accounts, no network, no IT. You export your own mail, the tool reads the files.

1. Make a folder, e.g. `~/Desktop/mail-export`.
2. In Outlook, select messages → **drag them onto that folder** (each becomes a `.eml` file).
3. Run:
```bash
python3 scripts/run_ingest.py --source files --path ~/Desktop/mail-export --me YOUR_EMAIL --no-gemma
```

### B. Personal Gmail
Enable IMAP in Gmail, make an [App Password](https://support.google.com/accounts/answer/185833), put
`IMAP_USER` / `IMAP_PASS` in `backend/.env` (copy from `.env.example`), then:
```bash
python3 scripts/run_ingest.py --source imap --days 30 --me YOUR_EMAIL --no-gemma
```

### C. Classic Outlook desktop on **Windows**
Outlook open + signed in (classic, not "New Outlook"):
```bash
python scripts\run_ingest.py --source outlook-local --days 30 --limit 3000 --me YOUR_EMAIL --no-gemma
```

### D. Work / Microsoft 365 mailbox (needs IT)
Programmatic access to a managed mailbox is controlled by your organization. Ask IT to register
an app (or consent Mail.Read), then use `--source outlook`. See [docs/outlook-setup.md](docs/outlook-setup.md).
Don't try to bypass an org block — use the manual-export path (A) instead.

---

## Step 2 — see it

```bash
python3 scripts/export_ui.py --out ../prototype/data.json
cd ../prototype
python3 -m http.server 4178
```
Open **http://localhost:4178/** → log in (`admin` / `password`).

Step 1 writes your data into `prototype/data.json`; the UI reads it. To refresh: re-run Step 1
(without `--no-gemma` once Ollama is set up) + the export, then reload the page.

---

## Privacy & cleanup

- Your mail is copied into a local file: `backend/inboxzero.db`. It stays on your machine —
  not sent to any third party. (The `files`/`outlook-local` paths make **no** network calls at all.)
- It's a plain SQLite file (relies on your disk encryption). To wipe everything:
  ```bash
  rm backend/inboxzero.db prototype/data.json
  ```
- **Never commit `inboxzero.db` or `prototype/data.json`** — they hold real mail and are gitignored.
- Using a **work** mailbox? Whether company mail belongs in a local tool is your org's policy
  call. The manual-export path keeps it offline, but it's still a local copy — check with IT if unsure.

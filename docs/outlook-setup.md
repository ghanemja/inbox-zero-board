# Connect a real Outlook mailbox (test user)

Read-only (`Mail.Read`), local-first. Mail is pulled to an on-device SQLite file,
classified by local Gemma, and shown in the prototype UI. Nothing is sent; nothing
leaves the machine except the one Graph read.

## A. Register an Azure app (once, ~5 min)

1. https://portal.azure.com → **Azure Active Directory → App registrations → New registration**.
2. Name: `inbox-zero-board`. **Supported account types:**
   - Test user is an Outlook.com / personal or cross-tenant account → *Accounts in any org directory and personal Microsoft accounts* → tenant stays `common`.
   - Test user is in one work/school tenant → *Accounts in this organizational directory only* → note the **Directory (tenant) ID**.
   - Leave **Redirect URI** empty (device-code is a public client).
3. **Authentication → Advanced settings → Allow public client flows → Yes.** (Device-code needs this.)
4. **API permissions → Add a permission → Microsoft Graph → Delegated → `Mail.Read`.**
   If the tenant requires it, click **Grant admin consent** (otherwise the user consents at sign-in).
5. **Overview** → copy **Application (client) ID** and (if single-tenant) the **Directory (tenant) ID**.

## B. Local machine

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
#   AZURE_CLIENT_ID=<application client id>
#   AZURE_TENANT_ID=common   (or the tenant id for single-tenant)

# local model for good triage (rules-only works but dumps most mail to needs_review)
#   install Ollama from https://ollama.com, then:
ollama pull gemma3:4b
#   (ollama serve must be running)
```

## C. Pull + classify the test user's real mail

```bash
# from backend/, venv active
python scripts/run_ingest.py --source outlook --me TESTUSER@DOMAIN.COM --limit 100
```

- Prints: *"To sign in, use a web browser to open https://microsoft.com/devicelogin and enter code XXXX."*
- The **test user** opens that URL, signs in, and consents to `Mail.Read`.
- The pull runs, classifies, and learns. First run is slow (Gemma per ambiguous email).
- `--me` must be the test user's primary SMTP address, so "from me" detection works.
- Quick smoke test without Ollama: add `--no-gemma` (triage will be rough).

## D. Show it in the UI

```bash
python scripts/export_ui.py --out ../prototype/data.json   # DB → UI data
# serve the prototype locally (from repo root):
python3 -m http.server 4178 --directory prototype
# open http://localhost:4178/  → log in → board now shows real mail
```

The UI loads `data.json` over its demo seed (per key). `data.json` is **gitignored** — keep it that way.

## Guardrails

- `backend/inboxzero.db` and `prototype/data.json` hold the test user's real mail. **Both are gitignored. Never commit or push them** — pushing `data.json` would publish their inbox on the public GitHub Pages site.
- Read-only: the app never sends or modifies mail. UI actions (resolve/nudge/mark-done) are local display state only.
- To wipe: delete `backend/inboxzero.db` and `prototype/data.json`.

## Known limits on real data (today)

- **Email only** — Slack/Jira/Calendar are seed-only until those connectors exist; every real item shows channel=email.
- **Delegate empty at first** — playbooks learn only after you actually delegate.
- **Viewer, not actor** — the UI shows real mail; resolve/nudge/mark-done are local display state and don't write back or send.

## Already handled for real mail

- **Clean text bodies** — pulls bodies as plain text (`Prefer: outlook.body-content-type="text"`) with an HTML-strip fallback, so the classifier sees clean text.
- **No re-login each run** — the MSAL refresh token is cached to `backend/.token_cache.json` (gitignored); subsequent runs acquire silently.
- **Projects from real threads** — emails are clustered by `conversationId`; any thread of ≥3 messages becomes a Project automatically (subject de-`Re:`d).

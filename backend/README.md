# Inbox Zero Board — backend

Local-first engine that turns an Outlook inbox into the To-Do / Awareness / Projects board, the relationship graph, and the Delegate routing — **without any email leaving the machine**.

```
Outlook (MS Graph)  →  local SQLite store  →  rules → Gemma (Ollama) → confidence gate  →  board + profiles + playbooks
```

Everything after the Graph pull runs on-device. The only network call is the authenticated Graph fetch to Microsoft; classification, extraction, and learning use a local Gemma model via Ollama. See [`../docs/learning-logic.md`](../docs/learning-logic.md) for the algorithm this implements.

## Layout

| File | Role | Status |
|---|---|---|
| `inboxzero/store.py` | SQLite schema + access (emails, classifications, contacts, playbooks) | functional |
| `inboxzero/rules.py` | Layer 1 — deterministic classification on structured signals | functional |
| `inboxzero/gemma.py` | Layer 2 — local Gemma via Ollama, JSON-schema-constrained, temp=0 | functional (needs Ollama) |
| `inboxzero/classify.py` | Orchestrator — rules → Gemma → confidence gate, logs reasoning | functional |
| `inboxzero/graph_client.py` | Outlook pull via MSAL device-code auth | scaffold (auth flow real, needs app reg) |
| `inboxzero/profiles.py` | Contact-profile learning (domains, required fields, tone) | scaffold + TODOs |
| `inboxzero/playbooks.py` | Playbook clustering + ticket replay | scaffold + TODOs |
| `inboxzero/pipeline.py` | Ingest loop tying it together | functional |
| `scripts/run_ingest.py` | CLI entry — pull + classify | functional |
| `scripts/seed_demo.py` | Load the prototype's fake emails so you can run with no inbox | functional |

## Setup

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# local model (one-time)
# install Ollama from https://ollama.com then:
ollama pull gemma3:4b

cp .env.example .env   # fill in AZURE_CLIENT_ID / TENANT_ID for real Outlook
```

## Run

```bash
# no inbox yet? load the prototype's seed emails and classify them:
python scripts/seed_demo.py
python scripts/run_ingest.py --source db --limit 50

# real Outlook (after app registration):
python scripts/run_ingest.py --source outlook --limit 100
```

Output lands in `inboxzero.db`. Point the prototype UI at an export of the `classifications` table to replace its fake seed data.

## Privacy posture (the leadership bar)

- Mail bodies stay in the local SQLite file; nothing is sent to any cloud LLM.
- Every classification row stores its `reasoning` + `confidence` + which layer decided → fully auditable.
- Below-threshold items are marked `needs_review`, never auto-actioned.
- Graph access uses delegated, read-scoped tokens (`Mail.Read`); no write scope by default.

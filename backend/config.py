"""Central config, loaded from .env (see .env.example)."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # .env optional; env vars / defaults still work (stdlib-only smoke test)

# Default to Microsoft's PUBLIC "Microsoft Graph Command Line Tools" client — the same
# first-party app Graph PowerShell uses. Lets you sign in + consent with NO app
# registration / no Azure portal. Override AZURE_CLIENT_ID in .env to use your own app.
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "14d82eec-204b-4c2f-b7e8-296a70dab67e")
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "organizations")  # work/school accounts
GRAPH_SCOPES = ["Mail.Read"]  # read-only by design
# MSAL token cache on disk → no re-login each run. Holds refresh tokens; gitignored.
TOKEN_CACHE = os.getenv("TOKEN_CACHE", os.path.join(os.path.dirname(__file__), ".token_cache.json"))

# Direct IMAP (Gmail / any provider) — no Outlook, no Azure. Gmail: app password.
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_USER = os.getenv("IMAP_USER", "")
IMAP_PASS = os.getenv("IMAP_PASS", "")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
GEMMA_MODEL = os.getenv("GEMMA_MODEL", "gemma3:4b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "300"))   # per-request seconds (slow hardware / cold load)
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "15m")  # keep model loaded between emails

CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))
PLAYBOOK_MATCH_THRESHOLD = float(os.getenv("PLAYBOOK_MATCH_THRESHOLD", "0.75"))
DB_PATH = os.getenv("DB_PATH", "inboxzero.db")

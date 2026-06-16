"""Central config, loaded from .env (see .env.example)."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # .env optional; env vars / defaults still work (stdlib-only smoke test)

AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "common")
GRAPH_SCOPES = ["Mail.Read"]  # read-only by design

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
GEMMA_MODEL = os.getenv("GEMMA_MODEL", "gemma3:4b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))
PLAYBOOK_MATCH_THRESHOLD = float(os.getenv("PLAYBOOK_MATCH_THRESHOLD", "0.75"))
DB_PATH = os.getenv("DB_PATH", "inboxzero.db")

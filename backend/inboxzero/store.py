"""SQLite store — the only place email data lives. On-device, auditable.

Tables:
  emails           raw pulled messages (id, from, to, cc, subject, body, headers, received)
  classifications  one row per email: board, reasoning, confidence, deciding layer
  contacts         learned per-person profile (domains, templates) as JSON blobs
  playbooks        learned ticket->subtasks mappings as JSON blobs

Contacts/playbooks store JSON for now; promote hot fields to columns when query
patterns settle. See docs/learning-logic.md §1 for the conceptual model.
"""
import json
import sqlite3
from contextlib import contextmanager

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS emails (
  id            TEXT PRIMARY KEY,
  from_addr     TEXT,
  to_addrs      TEXT,      -- json list
  cc_addrs      TEXT,      -- json list
  subject       TEXT,
  body          TEXT,
  has_unsub     INTEGER,   -- List-Unsubscribe header present
  is_reply      INTEGER,
  received      TEXT
);
CREATE TABLE IF NOT EXISTS classifications (
  email_id      TEXT PRIMARY KEY REFERENCES emails(id),
  board         TEXT,      -- todo | awareness | project | archive | needs_review
  task          TEXT,      -- extracted action (nullable)
  due           TEXT,      -- extracted due date (nullable)
  project_key   TEXT,      -- cluster id when board=project (nullable)
  topics        TEXT,      -- json list
  reasoning     TEXT,      -- human-readable "why" (the audit chip)
  layer         TEXT,      -- rules | gemma
  confidence    REAL,
  decided_at    TEXT
);
CREATE TABLE IF NOT EXISTS contacts (
  email_addr    TEXT PRIMARY KEY,
  profile       TEXT       -- json: {name, role, domains[], request_templates[], counts}
);
CREATE TABLE IF NOT EXISTS playbooks (
  goal          TEXT PRIMARY KEY,
  spec          TEXT       -- json: {learned, subtasks[], support, confidence}
);
CREATE TABLE IF NOT EXISTS commitments (
  id            TEXT PRIMARY KEY,
  party         TEXT,      -- 'them' (they owe you) | 'you' (you owe them)
  counterpart   TEXT,      -- email_addr of the other person
  what          TEXT,      -- the promised/requested thing
  channel       TEXT,      -- email | slack | jira | cal
  due           TEXT,      -- extracted due (nullable)
  status        TEXT,      -- open | done
  source_email  TEXT,
  created_at    TEXT
);
"""


@contextmanager
def db(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init(path=DB_PATH):
    with db(path) as conn:
        conn.executescript(SCHEMA)


def upsert_email(conn, e: dict):
    conn.execute(
        """INSERT OR REPLACE INTO emails
           (id, from_addr, to_addrs, cc_addrs, subject, body, has_unsub, is_reply, received)
           VALUES (:id,:from_addr,:to_addrs,:cc_addrs,:subject,:body,:has_unsub,:is_reply,:received)""",
        {**e, "to_addrs": json.dumps(e["to_addrs"]), "cc_addrs": json.dumps(e["cc_addrs"])},
    )


def save_classification(conn, c: dict):
    conn.execute(
        """INSERT OR REPLACE INTO classifications
           (email_id, board, task, due, project_key, topics, reasoning, layer, confidence, decided_at)
           VALUES (:email_id,:board,:task,:due,:project_key,:topics,:reasoning,:layer,:confidence,:decided_at)""",
        {**c, "topics": json.dumps(c.get("topics", []))},
    )


def get_contact(conn, addr: str) -> dict | None:
    row = conn.execute("SELECT profile FROM contacts WHERE email_addr=?", (addr,)).fetchone()
    return json.loads(row["profile"]) if row else None


def save_contact(conn, addr: str, profile: dict):
    conn.execute(
        "INSERT OR REPLACE INTO contacts (email_addr, profile) VALUES (?,?)",
        (addr, json.dumps(profile)),
    )


def iter_emails(conn):
    for row in conn.execute("SELECT * FROM emails"):
        d = dict(row)
        d["to_addrs"] = json.loads(d["to_addrs"] or "[]")
        d["cc_addrs"] = json.loads(d["cc_addrs"] or "[]")
        yield d


def save_commitment(conn, c: dict):
    conn.execute(
        """INSERT OR REPLACE INTO commitments
           (id, party, counterpart, what, channel, due, status, source_email, created_at)
           VALUES (:id,:party,:counterpart,:what,:channel,:due,:status,:source_email,:created_at)""",
        c,
    )


def list_commitments(conn, status="open"):
    rows = conn.execute("SELECT * FROM commitments WHERE status=? ORDER BY created_at", (status,))
    return [dict(r) for r in rows]


def resolve_commitment(conn, cid: str):
    conn.execute("UPDATE commitments SET status='done' WHERE id=?", (cid,))

#!/usr/bin/env python3
"""Export the local DB into the prototype's data shape → prototype/data.json.

The prototype loads data.json if present and overrides its built-in demo seed
(per-key: any non-empty array replaces the corresponding seed). Run after ingest:

  python scripts/export_ui.py --out ../prototype/data.json

Note: with a rules-only run the To-Do board is thin (addressed mail defers to
Gemma). Run ingest WITH Ollama to populate tasks/topics fully.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inboxzero import store, profiles, commitments  # noqa: E402

_FORMAL_SIGN = {"Best Regards", "Kind Regards", "Warm Regards", "Regards"}
_FORMAL_GREET = {"Dear", "Hello", "Good Morning", "Good Afternoon"}


def _init(name: str) -> str:
    parts = [p for p in name.replace("@", " ").replace(".", " ").split() if p]
    return (parts[0][0] + parts[1][0]).upper() if len(parts) >= 2 else name[:2].upper()


def export(db_path: str) -> dict:
    todos, aware, projects, people = [], [], [], []
    with store.db(db_path) as conn:
        rows = conn.execute("""SELECT c.*, e.subject, e.from_addr
                               FROM classifications c JOIN emails e ON e.id=c.email_id""").fetchall()
        for r in rows:
            if r["board"] == "todo":
                due = r["due"]
                todos.append({"id": r["email_id"], "cls": "soon" if due else "todo",
                              "title": r["task"] or r["subject"], "owner": "You", "team": "Inbox",
                              "due": due or "no date", "pill": ["amber" if due else "gray", due or "no date"],
                              "from": r["from_addr"], "subj": r["subject"], "body": "",
                              "why": [r["reasoning"]], "thread": []})
            elif r["board"] in ("awareness", "needs_review"):
                aware.append({"id": r["email_id"], "t": r["subject"],
                              "s": r["reasoning"], "team": "Inbox", "done": False})
            elif r["board"] == "project":
                projects.append({"id": r["email_id"], "t": r["subject"], "team": "Inbox",
                                 "owner": "You", "s": r["reasoning"], "pct": 10,
                                 "status": ["proj", "new"], "miles": [["now", "triage"]],
                                 "tasks": [["o", r["task"] or "follow up"]], "emails": [r["subject"]]})

        idx = {}
        for cr in conn.execute("SELECT email_addr, profile FROM contacts"):
            p = json.loads(cr["profile"])
            tot = p["counts"]["sent"] + p["counts"]["recv"]
            cs = profiles.comm_style(p)
            formality = 2 if (cs["greet"] in _FORMAL_GREET or cs["signoff"] in _FORMAL_SIGN) else 1
            init = _init(p.get("name") or cr["email_addr"])
            idx[cr["email_addr"]] = init
            people.append({"n": p.get("name") or cr["email_addr"], "r": p.get("role", ""),
                           "team": "Inbox", "inf": 2 if tot >= 40 else 1 if tot >= 20 else 0,
                           "sent": p["counts"]["sent"], "recv": p["counts"]["recv"],
                           "init": init, "channel": cs["channel"], "trend": "steady",
                           "domains": list(p.get("domains", {}).keys()),
                           "style": {"formality": formality, "len": cs["len"], "channel": cs["channel"],
                                     "greet": cs["greet"] or "Hi", "signoff": cs["signoff"] or "Thanks,",
                                     "emoji": cs["emoji"], "cadence": "—"}})

        commits = []
        for c in store.list_commitments(conn, "open"):
            level, label = commitments.sla(c["due"])
            commits.append({"id": c["id"], "party": c["party"],
                            "who": idx.get(c["counterpart"], _init(c["counterpart"])),
                            "what": c["what"], "chan": c["channel"], "sla": [level, label],
                            "cls": "overdue" if level == "red" else "soon" if level == "amber" else "",
                            "ctx": "from thread"})

    return {"todos": todos, "aware": aware, "projects": projects,
            "people": people, "commitments": commits}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=store.DB_PATH)
    ap.add_argument("--out", default="../prototype/data.json")
    args = ap.parse_args()
    data = export(args.db)
    with open(args.out, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote {args.out}: "
          + ", ".join(f"{len(v)} {k}" for k, v in data.items()))


if __name__ == "__main__":
    main()

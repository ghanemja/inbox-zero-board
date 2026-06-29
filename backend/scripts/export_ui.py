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

from datetime import datetime, timezone  # noqa: E402

from inboxzero import store, profiles, commitments, graph  # noqa: E402

_FORMAL_SIGN = {"Best Regards", "Kind Regards", "Warm Regards", "Regards"}
_FORMAL_GREET = {"Dear", "Hello", "Good Morning", "Good Afternoon"}


def _init(name: str) -> str:
    parts = [p for p in name.replace("@", " ").replace(".", " ").split() if p]
    return (parts[0][0] + parts[1][0]).upper() if len(parts) >= 2 else name[:2].upper()


def _strip_re(subject: str) -> str:
    s = subject or ""
    while True:
        low = s.lstrip().lower()
        if low.startswith(("re:", "fw:", "fwd:")):
            s = s.lstrip()[s.lstrip().find(":") + 1:]
        else:
            return s.strip() or "(thread)"


def export(db_path: str, me: str = "you@acme.com") -> dict:
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
        # Projects from real threads: cluster emails by conversationId; a thread with
        # >= MIN_THREAD messages becomes a project (auto-grouped, deterministic).
        MIN_THREAD = 3
        convs = {}
        for e in conn.execute("SELECT subject, conversation_id, received FROM emails "
                              "WHERE conversation_id IS NOT NULL AND conversation_id != '' "
                              "ORDER BY received"):
            convs.setdefault(e["conversation_id"], []).append(e["subject"] or "(no subject)")
        for cid, subjects in convs.items():
            if len(subjects) < MIN_THREAD:
                continue
            title = _strip_re(subjects[-1])
            projects.append({"id": "conv-" + _init(cid) + str(len(subjects)), "t": title, "team": "Inbox",
                             "owner": "You", "s": f"{len(subjects)} emails in thread",
                             "pct": min(90, 20 + len(subjects) * 8), "status": ["proj", "active"],
                             "miles": [["now", "active"]],
                             "tasks": [["o", "follow up on thread"]],
                             "emails": list(dict.fromkeys(subjects))[:6]})

        now = datetime.now(timezone.utc)
        rel = graph.relationship_metrics(conn, me, now)            # thread-aware, one pass
        open_ask_addrs = {c["counterpart"] for c in store.list_commitments(conn, "open")}
        idx = {}
        for cr in conn.execute("SELECT email_addr, profile FROM contacts"):
            addr = cr["email_addr"]
            p = json.loads(cr["profile"])
            tot = p["counts"]["sent"] + p["counts"]["recv"]
            cs = profiles.comm_style(p)
            formality = 2 if (cs["greet"] in _FORMAL_GREET or cs["signoff"] in _FORMAL_SIGN) else 1
            init = _init(p.get("name") or addr)
            idx[addr] = init
            series = graph.weekly_series(conn, addr, now)
            its = store.interactions_for(conn, addr)
            channels = sorted({it["channel"] for it in its}) or [cs["channel"]]
            days_quiet = (now - graph._parse(its[-1]["ts"])).days if its else None
            domains = p.get("domains", {})
            dominant = max(domains, key=lambda d: domains[d].get("support", 0)) if domains else None
            r = rel.get(addr, {})
            people.append({"n": p.get("name") or addr, "r": p.get("role", ""),
                           "team": "Inbox", "inf": 2 if tot >= 40 else 1 if tot >= 20 else 0,
                           "sent": p["counts"]["sent"], "recv": p["counts"]["recv"],
                           "init": init, "channel": cs["channel"], "channels": channels,
                           "series": series, "trend": graph.trend(series), "dormant": graph.dormant(series),
                           "recentVol": sum(series[-4:]), "daysQuiet": days_quiet,
                           "domains": list(domains.keys()), "dominantTopic": dominant,
                           "hasOpenAsk": addr in open_ask_addrs,
                           "yourLatencyH": r.get("your_latency_h"), "theirLatencyH": r.get("their_latency_h"),
                           "replyPairs": r.get("reply_pairs", 0), "responseRate": r.get("response_rate"),
                           "openLoops": r.get("open_loops", 0), "openLoopSubjects": r.get("open_loop_subjects", []),
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
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=store.DB_PATH)
    ap.add_argument("--out", default="../prototype/data.json")
    ap.add_argument("--me", default=os.getenv("ME", "you@acme.com"),
                    help="your email (same as ingest) — needed for reply-time / who-owes-whom metrics")
    args = ap.parse_args()
    data = export(args.db, args.me)
    with open(args.out, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote {args.out}: "
          + ", ".join(f"{len(v)} {k}" for k, v in data.items()))


if __name__ == "__main__":
    main()

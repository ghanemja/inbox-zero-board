#!/usr/bin/env python3
"""Drive profiles + playbooks with synthetic data — proves the learning code works
without needing Ollama or a real inbox. Run: python scripts/test_learning.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inboxzero import store, profiles, playbooks, gemma  # noqa: E402

ME = "you@acme.com"
DB = "test_learning.db"
store.DB_PATH = DB  # noqa


def main():
    if os.path.exists(DB):
        os.remove(DB)
    store.init(DB)

    with store.db(DB) as conn:
        # --- profile learning: 3 past catering requests to Rosa ---
        rosa = "rosa@cater.co"
        for i in range(3):
            email = {"from_addr": ME, "to_addrs": [rosa], "cc_addrs": [],
                     "subject": "Catering", "body": f"Hi Rosa — catering request {i}."}
            extracted = {"topics": ["catering"], "request_type": "catering request",
                         "slots": {"headcount": 12, "budget_code": "MKT-204"}}
            profiles.observe(conn, email, ME, extracted)
        # one reply FROM Rosa asking for dietary info → required via they_asked
        profiles.observe(conn, {"from_addr": rosa, "to_addrs": [ME], "cc_addrs": [],
                                "subject": "re: Catering", "body": "Any dietary needs?"},
                         ME, {"topics": ["catering"], "request_type": "catering request",
                              "asked_for": ["dietary"]})

        prof = store.get_contact(conn, rosa)
        req = profiles.required_fields(prof, "catering request")
        print("Rosa domains:", profiles.owned_domains(conn, rosa))
        print("Rosa required fields for 'catering request':", req)
        assert "headcount" in req and "budget_code" in req, "recurring slots should be required"
        assert "dietary" in req, "they_asked slot should be required"

        # also teach Fran a room domain so routing can find her
        for i in range(4):
            profiles.observe(conn, {"from_addr": ME, "to_addrs": ["fran@acme.com"], "cc_addrs": [],
                                    "subject": "Room", "body": "Hi Fran — room please."},
                             ME, {"topics": ["room booking"], "request_type": "room booking"})

        # --- playbook learning: two sponsor-meeting events ---
        ev1 = [{"task": "Order catering", "contact": rosa, "domain": "catering", "fields": ["headcount", "budget_code"]},
               {"task": "Reserve a room", "domain": "room booking", "fields": ["date", "headcount"]},
               {"task": "One-off favor", "contact": "bob@acme.com", "domain": None, "fields": []}]
        ev2 = [{"task": "Order catering", "contact": rosa, "domain": "catering", "fields": ["dietary"]},
               {"task": "Reserve a room", "domain": "room booking", "fields": ["AV"]}]
        playbooks.learn_from_sent_batch(conn, "sponsor meeting", ev1)
        playbooks.learn_from_sent_batch(conn, "sponsor meeting", ev2)

        plan = playbooks.replay(conn, "Create sponsor meeting",
                                {"headcount": 12, "budget_code": "MKT-204", "date": "Jul 18"}, ME)
        print("\nReplay 'Create sponsor meeting' (support =", plan["support"], "):")
        for st in plan["subtasks"]:
            print(f"  - {st['task']:16} → {st['contact'] or '(needs owner)':18} "
                  f"status={st['status']:12} missing={st['missing']}")

        tasks = {s["task"] for s in plan["subtasks"]}
        assert "Order catering" in tasks and "Reserve a room" in tasks, "recurring asks kept"
        assert "One-off favor" not in tasks, "one-off (1 event) should be generalized out"
        room = next(s for s in plan["subtasks"] if s["task"] == "Reserve a room")
        assert room["contact"] == "fran@acme.com", "room should route to Fran via domain ownership"

        # --- fuzzy playbook match via embeddings (monkeypatched embedder, no Ollama) ---
        gemma.embed = lambda t: [1.0, 0.0] if "sponsor" in t.lower() else [0.0, 1.0]
        playbooks.learn_from_sent_batch(conn, "sponsor meeting", ev2)  # re-learn → stores centroid
        fuzzy = playbooks.replay(conn, "Set up a sponsor gathering",  # NOT an exact key match
                                 {"headcount": 12}, ME)
        print("\nFuzzy match 'Set up a sponsor gathering' →",
              "matched playbook" if fuzzy else "no match")
        assert fuzzy is not None, "embedding NN should match the sponsor playbook despite different wording"
        assert "Order catering" in {s["task"] for s in fuzzy["subtasks"]}

    os.remove(DB)
    print("\nAll learning assertions passed ✓")


if __name__ == "__main__":
    main()

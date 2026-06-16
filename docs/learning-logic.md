# Learning logic — how email history becomes routing + playbooks

How a sent/received email turns into the two things Delegate relies on:
1. **Contact profiles** — who handles what, and what details they need.
2. **Playbooks** — how a ticket goal decomposes into routed asks.

Everything runs **local** (Outlook pull → on-device store → local Gemma + local embeddings). Nothing leaves the machine. Every learned fact carries a support count + confidence so leadership can audit it and the system never fabricates.

---

## 1. Data model

```
Contact {
  email, name, role_inferred,
  domains: [{ label, support, confidence, last_seen }],          // what they handle
  request_templates: [{
    type,                       // e.g. "catering request"
    required_fields: [{ name, support, source }],   // source: 'recurring' | 'they_asked'
    tone_exemplars: [string],   // 2-3 of your past openers to them
    avg_turnaround_h
  }],
  counts: { sent, recv }
}

Playbook {
  goal,                         // canonical, e.g. "sponsor meeting"
  cluster_id,                   // which thread-cluster it generalizes
  subtasks: [{ task, contact_email, request_type, fields_needed: [name] }],
  support,                      // # of past events it generalizes
  confidence
}

Ticket { goal_text } → match → Playbook → fill → Draft[]
```

Store: SQLite or flat JSON on-device. Embeddings: local model (e.g. `nomic-embed-text` via Ollama) for clustering threads/tickets.

---

## 2. Ingestion pipeline (per email)

```
on_email(msg):
  rules_extract(msg)        # structured, free, deterministic
  if ambiguous: gemma_extract(msg, temp=0, schema=...)   # only when rules can't decide
  update_contact_profile(msg, extracted)
  if msg is part of a known event-cluster: update_playbook(cluster)
```

### Signals that build a **contact profile**

| Learned field | Signal | Rule |
|---|---|---|
| `domains[]` | Gemma topic-label of body | Contact "owns" a domain when they're your top counterpart for it **and** support ≥ 3 threads. |
| `required_fields[]` (recurring) | Entity diff across past requests of same type | A field present in ≥ ⌈0.6·M⌉ of M past requests → required. `source:'recurring'`. |
| `required_fields[]` (they asked) | Their reply contains a question for a missing slot ("what's the budget code?") | Mark required immediately, high weight. `source:'they_asked'`. |
| `tone_exemplars` | Your sent openers to them | Keep last 2-3 as draft seeds (mirror your real voice). |
| `avg_turnaround_h` | time(their_reply) − time(your_send) | Rolling average. Feeds Insights + reliability flags. |

### Entity extraction (the "slots")

Per request type, pull a typed slot set: `date, time, headcount, location, budget_code, dietary, attendee_list, AV_needs, deadline, attachments`. Rules grab the obvious (dates, codes via regex); Gemma fills the rest. Each slot stored with the value + which email it came from (provenance → auditable).

---

## 3. Playbook learning (ticket → asks)

**Capture:** when you file ticket *X* and send a batch of asks, record the tuple
`{goal:X, subtasks:[{task, contact, fields}]}` as one observed event.

**Generalize:** embed past event threads + their subtask sets. Cluster (cosine ≥ τ). A cluster of ≥2 similar events ("Q1 sponsor lunch", "Q3 sponsor dinner") collapses into a canonical playbook whose `subtasks` = the asks that recur across the cluster (union, weighted by frequency). `support` = cluster size.

**Replay:** new ticket → embed goal_text → nearest playbook above threshold.
```
for subtask in playbook.subtasks:
    contact   = subtask.contact (or re-route via domain match if contact left/changed)
    fields    = fill(subtask.fields_needed, from = ticket_slots ∪ contact.request_template defaults)
    missing   = fields where value is None and field.required
    draft     = template(contact.tone_exemplars, fields)
    status    = missing ? 'needs detail' : contact ? 'ready' : 'needs owner'
```

---

## 4. Reliability guards (the leadership bar)

- **Confidence gate.** Every inference has `confidence = f(support, recency, correction_history)`. Below threshold → *suggested*, never auto-sent.
- **Never fabricate.** A missing required field is flagged `[fill in]`, never guessed.
- **No-owner safety.** No contact above domain-match threshold → "pick person", never routes to a stranger.
- **Provenance everywhere.** Each routing/field shows its evidence ("booked via her 6×", "she asked for this in Mar thread"). Fully auditable.
- **Correction loop.** User edits (reassign person, add/drop field, fix value) are the strongest signal — applied immediately and weighted above passive observation. Corrections also retro-adjust the playbook.

---

## 5. Cold start

- **No history:** rules-only classification; Delegate has no playbook → Gemma decomposes the ticket generically, routes by any weak domain match, and *learns the real routing after you send the first batch.*
- **New contact:** profile seeded from role inference + org directory; templates fill in as threads accrue.
- A playbook is only trusted at `support ≥ 2`; below that it's labelled "first run — will learn from your edits."

---

## 6. Update algorithm (sketch)

```python
def update_contact_profile(contact, msg, ext):
    for topic in ext.topics:
        d = contact.domains.setdefault(topic, Domain(support=0))
        d.support += 1; d.last_seen = msg.date
        d.confidence = conf(d.support, d.last_seen)

    if ext.request_type:
        tpl = contact.templates.setdefault(ext.request_type, Template())
        tpl.observe(ext.slots)                     # recurrence stats per slot
        if msg.is_reply and ext.asked_for:         # they requested a missing slot
            tpl.mark_required(ext.asked_for, source='they_asked')
        if msg.from_me:
            tpl.tone_exemplars.add(first_sentence(msg))
        tpl.turnaround.push(reply_gap(msg))

def conf(support, last_seen):
    return min(1.0, support/5) * recency_decay(last_seen)
```

---

## 7. What the prototype fakes vs. what this spec builds

| Prototype (now) | Real build (this spec) |
|---|---|
| Hard-coded `people[].domains` | Learned from topic-labeled history |
| One `playbooks['sponsor meeting']` | Clustered + generalized from your sent events |
| Fields pre-marked ✓/? | Recurrence + "they-asked" inference |
| Static drafts | Templated from your real tone exemplars |

---

## 8. Commitments ledger (chief-of-staff layer)

Read promises/requests out of each message and track who owes whom — across every channel, not just email. `inboxzero/commitments.py`.

- **Direction.** `party='them'` (they owe you) when you asked or they promised you; `party='you'` (you owe them) when they asked or you promised them.
- **Detection.** Rules first (request/promise/due regexes — deterministic, testable). Gemma refines ambiguous cases via the same `asked_for` / `request_type` signals (hook marked in code).
- **SLA.** `sla(due, overdue_days)` → `(level, label)` badge; overdue → red, near-term → amber, else ok. Feeds the Commitments board + nudge prompts.
- **Storage.** `commitments` table (party, counterpart, what, channel, due, status). Resolved when a fulfilling reply lands (or user marks done).

## 9. Per-person communication style (compounding-graph moat)

`profiles.py` learns *how you write to each person* from your outgoing messages:

- **Signals** (from_me only): greeting, sign-off, message length, emoji rate, preferred channel, response cadence (turnaround samples).
- **Fingerprint.** `comm_style(profile)` summarizes → `{greet, signoff, len, emoji, channel, avg_words}`. Drafts + nudges mirror it, so an ask to a formal contact reads formal, a Slack-native one reads casual.
- **Why it's a moat.** This is per-relationship, accumulates with use, and is invisible to a generic assistant — part of the graph that can't be lifted out.

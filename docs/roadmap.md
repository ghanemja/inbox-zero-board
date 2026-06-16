# Roadmap — from inbox tool to local-first chief of staff

The product wins on the four things Microsoft structurally can't/won't copy (see the moat map).
Everything below is organized by which moat it deepens. ★ = building now into the prototype.

---

## Moat 4 — Chief-of-staff layer (category moat)

Reframe: not a smarter inbox, an accountability layer over every channel.

- ★ **Commitments ledger** — every promise made/received, across channels. Two lanes: *they owe you* / *you owe them*. SLA timers, overdue flags, one-click nudge. This is the headline chief-of-staff feature.
- ★ **Waiting-on tracking** — outbound asks that haven't been answered; auto-surface laggards.
- **Autonomous follow-up agent** — drafts the nudge, schedules the reminder, escalates if ignored. Approval-gated, fully audited.
- **Decision memory** — what was decided, by whom, where; linked to source thread + the commitments it created.
- **Daily brief** — "here's your day": what's owed, what's slipping, what to delegate. Morning chief-of-staff report.

## Moat 3 — Compounding org-graph (switching-cost moat)

The asset that grows per-customer and can't be lifted out.

- ★ **Per-person communication style** — formality, length, greeting/sign-off, directness, emoji, preferred channel, response cadence. Drafts + nudges mirror how *you* talk to *that* person. (Extends `tone_exemplars` → full style fingerprint.)
- ★ **Temporal graph** — relationships rising/fading, "new this week", dormant-but-important. The graph evolves; connections form and break over time.
- **Bottleneck + bus-factor detection** — who is the single point of failure for a topic/project; where work piles up.
- **Org playbook library** — learned "how we do X here" templates; shareable across the team. Tribal knowledge frozen into reusable routes.
- **Topic ownership map** — who owns what, with confidence + evidence; auto-updates as the org changes.

## Moat 2 — Cross-silo graph (integration moat)

One neutral graph spanning tools Microsoft won't deeply unify.

- ★ **Multi-channel ingest** — email + Slack/Teams + Jira/Linear + calendar + docs, normalized into one item stream and one graph. (Prototype: channel-tagged items + a Sources connector strip; real build: per-connector adapters.)
- **Unified person identity** — same human across Gmail address, Slack handle, Jira user → one node.
- **Cross-channel threads** — a Slack thread + the email + the ticket about the same thing, stitched into one project.

## Moat 1 — Local-first (business-model moat)

The thing their cloud business can't match.

- **Zero-egress guarantee** — on-device store + local model; a visible "nothing left this device" audit trail.
- **Explainable + gated** — every classification/route shows reasoning + confidence; low-confidence → review lane, never auto-acted.
- **Regulated-ready** — exportable audit log, on-prem deploy; the wedge for legal / healthcare / defense.

---

## Build order (this pass)

1. ★ **Commitments tab** (chief of staff) — owed-to-you / you-owe, SLA timers, nudge.
2. ★ **Comm-style fingerprint** — per-contact style card in Insights; Delegate drafts adopt it.
3. ★ **Cross-silo channels** — channel tags on items + graph; Sources connector strip.
4. ★ **Temporal graph cues** — rising/fading/new edges in Insights.
5. Backend: extend `profiles.py` (style learning) + new `commitments.py`; update `learning-logic.md`.

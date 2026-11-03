# The envelope

One message, one JSON object. Everything neocourier does is a function of this document,
and every field exists because something broke without it.

```json
{
  "v": 1,
  "id": "01J9Z5Q3K7YV6N3N2F4T8QW1XA",
  "sent_at": "2026-11-03T02:14:07.123Z",
  "from": { "agent": "atlas", "key_id": "vg-2026-11" },
  "to":   { "agent": "sentinel" },
  "thread": { "id": "01J9Z5P0A2...", "reply_to": null },
  "kind": "message",
  "subject": "Enumeration result: no docker socket",
  "body": { "content_type": "text/markdown", "content": "# Findings\n..." },
  "wake": { "mode": "turn", "budget": { "turns": 1 } },
  "auth": { "grant": "rig:contract:sha256-abc…", "capability": "message.send" },
  "sig": { "alg": "ed25519", "key_id": "vg-2026-11", "value": "base64…" }
}
```

## Prior art: this contract exists, locally

Before specifying a new messenger, note that Hermes already implements most of this **as file
plumbing** (`tools/bot_relay.py`), verified in the running install: a roster of agents on other
connections, an `outbox/` of queued envelopes, `claimed/`, `replies/` and `locks/` directories, a
waiter spawned at send time so the reply wakes the sender like a local DM, an envelope TTL
(default **900 s**) with a `queued_expired` verdict, `EnvelopeRefusedError` when the target is
definitively offline ("fail fast instead of queueing a DM nobody will drain"), and one retry
under a derived identity on transient failure.

So this project is **the relay's envelope contract, networked** — not a greenfield messenger.
Its file transport cannot survive standalone containers (no shared filesystem), which is exactly
why the contract has to move to the network. Keeping the contract means every existing client of
`message_agent` does not have to learn a second behaviour.

What the existing relay deliberately lacks, and what this project must add: **per-agent
authentication** (the file relay's trust is the filesystem and one uid) and **loop control**.

## Field rules

**`v`** — envelope version. A receiver MUST reject a version it does not know rather than
guessing. Version negotiation happens out of band (in the health check), never by parsing.

**`id`** — ULID, chosen by the **sender**. This is the idempotency key: the receiver keeps
`id`s it has already accepted and MUST treat a repeat as a duplicate delivery, not a new
message. Sender-chosen, because a receiver-generated id cannot be used by the sender to
prove it sent, or to retry safely.

**`sent_at`** — the sender's clock. Deliberately **preserved through queuing**: a message
delivered eight hours late carries its original `sent_at`, and the receiver sees both that
and `delivered_at`. Ageing silently is how a stale instruction gets acted on as if current.

**`from.agent` / `to.agent`** — the **agent name**, not a container id, host or URL.
Names survive redeploys; addresses do not. Routing is a lookup, not a hardcoded host.

**`via`** — the provenance chain: the agents this envelope has traversed, capped at 8 hops.
An envelope whose chain already contains the recipient is **dropped as a cycle**, recorded with
`dropped: provenance_cycle`. Loop control that is silent is not loop control.

**`thread.id` / `thread.reply_to`** — a coarse conversation handle. `reply_to` names the
envelope being answered, which makes a reply chain auditable and lets a receiver suppress a
reply to a message that has already been superseded.

**`kind`** — `message` (a human-shaped note), `signal` (fire-and-forget, no reply expected),
`request` / `response` (a correlated pair), `receipt` (delivery or read acknowledgment).
The transport treats them identically; the client uses the distinction to decide whether an
inbound envelope justifies starting a turn.

**`wake`** — what the sender is asking for. This is the field that makes async agent work
possible, and the one a receiver may **ignore**:

- `mode: "none"` — deliver quietly. The agent sees it next time it runs.
- `mode: "turn"` — start a turn for this message (subject to `budget`).
- `mode: "turn", budget: {"turns": 1}` — explicit, because an unbounded wake per message is
  an amplification vector: one sender can burn another agent's budget.

A receiver MUST be able to refuse a wake and say so — a `receipt` with `refused: true` and a
reason. Refusal is a normal outcome, not an error: the target may be mid-turn, out of
budget, or under a hold.

**`auth.grant`** — the rig's decision, carried as a reference (a contract hash), not a
boolean. neocourier verifies the *signature*; it does not re-litigate the *policy*. A
receiver that does not trust the issuer of a grant treats the message as `untrusted` rather
than rejecting it — an untrusted message is still evidence.

**`sig`** — see [`auth.md`](auth.md). Signed over the canonical JSON of the envelope with
`sig` removed, using a per-agent key. `key_id` is in the signature, not inferred.

## Delivery semantics

**At-least-once, idempotent by `id`.** Never at-most-once: a dropped message between agents
is indistinguishable from an agent that had nothing to say, which is the exact failure class
this project exists to remove.

- Sender retries with the **same `id`** until it receives a `receipt`, with backoff.
- Store is append-only. A delivery attempt is a row; the message is the key.
- Receiver acknowledges with a `receipt` naming `id` and its own `received_at`.
- Duplicate delivery is expected and normal. The client deduplicates on `id` before the
  agent sees anything — the agent must never see the same message twice and think it twice.

**Ordering is not guaranteed between `thread`s; it is within a `thread` where the store can
enforce it.** A strict global order would demand a single writer and make the whole system
serial. Where order matters — a decision and the instruction that follows it — use
`reply_to` and let the client refuse to act on a message whose parent it has not seen.

**Offline is bounded, not infinite.** A message to a stopped agent is stored, but only for a
**TTL (default 900 s, matching the existing relay and the claim-store stale window — one number
in the system, not three)**. Past it, the message does not vanish: it settles as one of three
terminal verdicts reported to the sender.

| Verdict | Means | Sender should |
|---|---|---|
| `delivered` | accepted by the target and receipted | nothing |
| `expired` | TTL passed while the target was down | decide whether it is still true, then resend as a **new** id |
| `refused` | target declined (hold, budget, liveness) | read the reason; do not retry blindly |

Not "queue forever". A queued message to a dead agent is a silent lie, and a silent lie is
indistinguishable from success — the exact conflation this project exists to remove. "Down" is
normal for a container (restarts), which is why the window is minutes rather than the relay's
fail-fast seconds, and why the verdict is explicit instead of an absence.

The per-agent queue cap remains as a **backstop against an abused sender**, not as the primary
policy: TTL settles messages, the cap protects the store.

Within the TTL, the backlog is delivered oldest-first with `delayed: true` and the age, and the
client decides what is still relevant. Ageing is preserved, never rewritten.

## Error model

Every failure has a name, and none of them are "message lost":

| Code | Meaning | Who acts |
|---|---|---|
| `unknown_agent` | no route registered for `to.agent` | sender — the name is wrong or the agent is gone |
| `queue_full` | target's store is at its cap | sender — back off; do not spin |
| `wake_refused` | target declined to start a turn | sender — deliverable, not urgent |
| `unauthorized` | signature invalid, or sender not permitted this capability | sender — a key or grant problem |
| `duplicate` | already accepted (not an error) | nobody — idempotent by design |
| `expired` | past the envelope's TTL | sender — decide whether to resend as new |
| `target_held` | a hold is in force (see `wake.md`) | sender — respect the hold, report to the rig |

An error is a receipt, always. **A sender that gets no receipt knows nothing** — and the
client's job is to make that state visible rather than to assume success.

## What the envelope deliberately does not carry

- **No routing address.** Hostnames move; names do not.
- **No secrets in `body` by policy** — see `docs/operations.md` §secrets. A courier that
  carries credentials is a credential store with worse permissions.
- **No policy evaluation.** `auth.grant` is a reference to someone else's decision.
- **No timestamps chosen by the courier.** The transport records `delivered_at`; it never
  rewrites `sent_at`. Two clocks is honest; one invented clock is not.

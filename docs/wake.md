# Wake: how a message starts a turn

An agent in its own container is, most of the time, not running a turn. A message that only
lands in a queue is a message that waits. **Wake** is the mechanism that turns delivery into
work — and the mechanism that can most easily be abused.

## The three ways a wake can happen

| Mode | Shape | When it is right |
|---|---|---|
| **Push webhook** | courier POSTs a signed `wake` to the agent's own HTTP surface | the agent has an addressable surface (the normal case in a rig) |
| **Pull long-poll** | agent holds a request open against the courier; a message completes it | the agent is unaddressable (NAT, no ingress, air-gapped) |
| **Sidecar signal** | courier writes to a local socket/file the agent's supervisor watches | agent and courier share a host or a network namespace |

All three deliver the *same* envelope. Wake is a delivery hint, never the delivery itself:
the agent always fetches the message by `id` from the store, so a malformed wake cannot
inject content and a lost wake cannot lose a message.

**That property is the whole design.** Wake carries an `id` and a signature, nothing else.

```
POST /neocourier/wake
{
  "id": "01J9Z5Q3K7YV6N3N2F4T8QW1XA",
  "to": "caravaggio",
  "reason": "turn",
  "issued_at": "2026-11-03T02:14:08Z",
  "nonce": "b7f3…",
  "sig": "base64…"        # courier's key, over the canonical body
}
→ 202 Accepted   {"id": "...", "accepted": true,  "mode": "turn"}
→ 409 Conflict   {"id": "...", "accepted": false, "reason": "already_running"}
→ 429 Too Many   {"id": "...", "accepted": false, "reason": "budget_exhausted", "retry_after": 60}
→ 423 Locked     {"id": "...", "accepted": false, "reason": "hold"}
```

`202` means "I will start a turn and pull that `id`". It never means "processed". The work is
done when the agent acknowledges the envelope with a `receipt`.

## Why the agent, not the courier, decides

A wake is a request. The agent's own surface answers it, and it can say no:

- **already running a turn** → `409`. The courier queues; the agent picks it up at the end of
  the current turn rather than interrupting it. Interrupting mid-turn is how you get half
  finished work and duplicated side effects.
- **budget exhausted** → `429`. Each agent has a wake budget from its rig contract (turns per
  hour, tokens per day). Without this, one chatty sender spends another agent's money.
- **under a hold** → `423`. An operator's hold ("do not start new work") outranks any sender,
  forever, including the CEO's. A hold that a message can override is not a hold.
- **wake mode `none`** → the agent acknowledges the receipt and starts nothing. Quiet
  delivery is a legitimate request.

## Loops, and why they are a wake problem

Two agents that wake each other are an infinite loop with a bill. Three defences, all cheap:

1. **`thread` depth.** An envelope carries `thread.depth`; past a configured ceiling (default
   8) the courier delivers but **never wakes**. The message is still read next run — the
   conversation can continue, it just cannot be a machine gun.
2. **Per-pair rate limit.** `A→B` wakes are limited (default: 5 per minute, burst 10). Over
   the limit: queue and deliver, no wake, one summary notice to the sender.
3. **Wake deduplication.** Multiple messages arriving for a stopped agent coalesce into
   **one** wake when the agent comes back, not N wakes. The wake says "you have 7 new
   messages, oldest 3h old" rather than replaying seven triggers.

The metric that matters is **wakes per delivered message**. It should be slightly above 1
(each wake yields at least the message it named) and if it climbs, something is looping.

## Offline behaviour

An agent whose container is stopped has no surface to wake. Messages accumulate in its store,
per-agent, and are delivered on its next start.

- The client on start asks for the backlog **oldest-first** with `delayed: true` and the age.
- The client, not the courier, decides what is still relevant: it may answer, note, or
  discard with a reason. Discarding is recorded — a silently forgotten message is
  indistinguishable from a lost one.
- Queue has a **cap per agent** (default 1,000 messages / 50 MB). At the cap, senders get
  `queue_full` and are expected to back off. The alternative — unbounded growth — turns a
  stopped agent into a disk-filling denial of service.

## Wake and the rig

The rig does not wake agents itself. It:

- **issues** the contract that carries each agent's wake budget and ceiling,
- **records** every wake refusal as an event (a refused wake is often the first sign that an
  agent is stuck, held, or being spammed),
- **displays** the state: awake, queued depth, last wake, last refusal.

That is the boundary: neocourier decides *how* to wake, the agent decides *whether*, and the
rig decides *what it was allowed to ask for*.

## Open questions

- **Wake on a schedule vs on a message.** Should the rig be able to say "wake at 09:00 with
  whatever is queued"? Likely yes — but it belongs in Hermes cron, not here.
- **Wake priority.** A held agent's purgatory is deliberate; should an operator wake
  override it? Current answer: no. A hold that a button can override is a suggestion.
- **Cross-host wake** needs a relay with its own signing key; see `transports.md`.

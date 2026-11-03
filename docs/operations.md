# Operations

What breaks, what it costs, and what an operator actually watches.

## Sizing, honestly

| Agents | Store | Daemon | Notes |
|---|---|---|---|
| 1–10 | SQLite, single file, backed up by copy | 1 process, 100 MB | the intended v0.1 target; one Docker host |
| 10–100 | Postgres | 1 process + 1 worker | the point where a single SQLite writer becomes the bottleneck |
| 100+ | Postgres, partitioned by `to.agent` | N workers | still no broker; the store is the queue |

The number that matters is not agents, it is **messages per second per receiver**. A receiver
processes one turn at a time, so anything above a few messages a second to one agent is
already queueing regardless of transport.

## What the operator sees

The rig's UI is the primary surface; the courier exposes metrics for it:

- `queue_depth{agent}` — rising means an agent is down, held, or slower than its mail.
- `wakes_total{agent,result}` — the refusal reasons (`already_running`, `budget_exhausted`,
  `hold`) are the early warning that an agent is stuck or spammed.
- `delivery_latency_seconds{agent}` — p50/p95 from `sent_at` to receipt. Watch p95, not mean.
- `duplicate_receipts_total` — expected to be non-zero. A sharp rise means senders are
  retrying hard, which means something upstream is timing out.
- `verification_failures{reason}` — should be zero. Any value is a security event, not a
  metric.
- `wakes_per_message` — near 1.0 is healthy. Climbing means a loop.

**The single most useful alert:** an agent whose queue depth is rising *and* whose wake
result is `already_running` for more than a few minutes. That agent is not slow, it is stuck.

## Backpressure

- Per-agent queue cap (default 1,000 / 50 MB). Senders get `queue_full` and back off.
- Per-pair wake rate limit (default 5/min). Over it: deliver, do not wake, notify the sender.
- Global ingress limit at the daemon, so one agent cannot starve the store for everyone.

Refusing is better than queueing forever. An unbounded queue converts one stopped agent into
a disk-full incident for the whole host.

## Loops

The failure mode with its own section because it is the one that costs money silently:

- `thread.depth` ceiling (default 8) stops the courier from waking past it.
- Per-pair rate limits cap the burst.
- A **loop detector**: if A→B→A repeats the same `thread` more than N times in M minutes, the
  courier refuses wakes for that thread, delivers the messages, and raises one event.
- The agent-level defence: a turn started by a wake should know its wake depth and be able to
  decline to reply. That belongs in the Hermes plugin, not the courier.

## Retention

- Delivered + acknowledged envelopes: kept 30 days by default, then compacted to a hash +
  metadata. The body is not the system of record; the agent's own transcript is.
- Undelivered: kept until acknowledged or explicitly dropped by an operator, with the drop
  recorded.
- **Never silently expire a message.** An expired message is a decision, and decisions get a
  reason and an actor.

## Secrets

**The courier does not carry credentials.** If a message body contains something that looks
like a token, the daemon flags it and stores a redacted copy with a pointer, because a
transport that carries secrets becomes a credential store with worse permissions.

The check is deliberately cheap and shallow — the known-prefix shapes (`gh[pousr]_`,
`sk-`, `AIza`, `xox`, JWT triplets, private-key headers). It exists to make the *accident*
loud, not to be a security boundary.

## Backup and recovery

- Store is the only state. Back it up like a database: dump, not file copy, for Postgres.
- Keys are **not** backed up with the store: keys live in the agents' containers and the
  public half in the registry. Losing the store loses history; losing a key loses identity,
  and those are different incidents with different responses.
- Recovery priority: registry (who exists) → store (what was said) → audit log.

## Failure drills worth running before 1.0

1. Kill the daemon mid-delivery; confirm no message is lost and duplicates are absorbed.
2. Stop an agent for an hour with 50 queued messages; confirm one coalesced wake, backlog
   oldest-first, ages intact.
3. Replay a captured envelope; confirm `duplicate`, not double delivery.
4. Corrupt a key; confirm `unauthorized` volume alerts rather than messages vanishing.
5. Loop two agents at each other; confirm the depth ceiling and rate limit both fire, and
   that the store does not grow without bound.

# Roadmap

Small and correct first. Each milestone is shippable and has a test that fails today.

## v0.1 — one host, real delivery

- [ ] Envelope schema + canonical JSON signing/verification (`docs/protocol.md`, `docs/auth.md`)
- [ ] Store: SQLite, append-only, idempotent on `id`, per-agent queue cap
- [ ] HTTP transport on the container network; unix socket as the second implementation
- [ ] Wake: signed POST to the agent's surface, `202/409/423/429`, coalesced backlog wakes
- [ ] Receipts: delivered, read, refused (with reason)
- [ ] CLI: `courier send|inbox|read|receipt|status` for debugging without an agent
- [ ] Acceptance: the five failure drills in `docs/operations.md`

**Not in v0.1:** relay, cross-host, SSE, loop detector, retention compaction, Postgres.

## v0.2 — the Hermes plugin

- [ ] Plugin exposing `courier_send`, `courier_inbox`, `courier_read`, `courier_receipt`,
      `courier_status` to the model
- [ ] Wake → turn path through the Hermes gateway, including budget and hold enforcement
- [ ] `message_agent` bridge: cross-container sends routed through the courier
- [ ] Read-back before receipt, so an acknowledgment always means "handled"

## v0.3 — many hosts

- [ ] Relay with its own signing key, hop chain preserved and visible
- [ ] SSE / long-poll transport for unaddressable agents
- [ ] Postgres store, partitioned by recipient
- [ ] Loop detector + per-thread wake refusal

## v1.0 — the version people can depend on

- [ ] Frozen envelope schema (v1 with a compatibility policy)
- [ ] Documented threat model with an external review
- [ ] Metrics contract the rig UI renders directly
- [ ] Migration path from "agents in one process" with no message loss

## Explicitly deferred

| Idea | Why not now |
|---|---|
| Broker-backed transport | a dependency to operate for a guarantee the store already gives |
| Exactly-once semantics | at-least-once + idempotency is honest; exactly-once is a lie with a retry counter |
| Rich typing / RPC over the courier | the courier moves messages; schemas belong to the senders |
| Built-in encryption at rest beyond the store's own | the store is the operator's database; encrypt it there |
| A courier UI | the rig is the UI; a second one would disagree with it |

## Non-goals, permanently

- Deciding who may talk to whom (that is the rig's contract).
- Starting work an agent did not agree to (wake is a request; the agent may refuse).
- Being the system of record for conversations (that is the agent's transcript).

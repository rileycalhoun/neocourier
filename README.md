# neocourier

**A courier for agents.** Reliable, authenticated message delivery between Hermes agents,
with wake-on-message so a message *starts a turn* instead of waiting to be polled.

**Shipping agent-to-agent messaging?** I do fixed-price reliability audits for teams running agents
in production: **$900, ten business days** — a written assessment plus patches for the highest-impact
failures, delivery guarantees included. Open an issue and I answer personally.

**This is a dependency, published separately rather than a second product.** It exists because
the transport deserves its own version number and a clean boundary — not because it is meant to
stand alone. Transport is a commodity: there are better-maintained buses than this one. What is
not commodity is *agent-aware* delivery — wake-on-message, proof of delivery, and the
distinction between "nothing arrived" and "nothing could arrive" — and that value is only
legible underneath a control plane that can act on it. The control plane is
[`hermes-rig`](https://github.com/rileycalhoun/hermes-rig); this is its delivery guarantee.

**Questions, design objections, or a delivery problem: [open an issue](https://github.com/rileycalhoun/neocourier/issues/new/choose).**
There is no email contact — an issue is the channel. Design objections are the most useful
thing you can send while this is still a specification.

Apache-2.0.

> A rig, in climbing, is the device that connects harnesses. `neocourier` is the rope
> between them: it moves a message from one agent to another and proves who sent it.
> It does not decide who may talk to whom — that is the [rig](https://github.com/rileycalhoun/hermes-rig)'s job.

## Why this exists

Hermes already has in-process bot messaging: agents in one gateway message each other
directly, because they share a process and a filesystem. That is fast and it is exactly as
durable as the process. The moment agents live in **separate containers** — which is the
rig's deployment model — the assumptions break:

| In one process | In separate containers |
|---|---|
| a message is a function call | a message is a network write that can be lost |
| the sender knows the recipient is alive | it may be mid-restart, or down for a day |
| identity is implicit (same uid) | identity must be proven per message |
| the recipient reads when it next runs | the recipient must be *woken* |

`neocourier` is the smallest thing that closes that gap: an envelope, a signature, a store,
and a delivery path with a wake.

## What it is not

- Not a gateway, not a control plane, not a scheduler. It never starts an agent's turn
  itself; it asks the agent's own surface to, and the agent decides.
- Not an LLM router. It does not know what a message means.
- Not an authorization system. It verifies *who sent it*; whether that sender was allowed to
  is the rig's ruling, stamped in the envelope.

## The shape

```
 agent A (container)                                        agent B (container)
 ┌──────────────────┐        ┌────────────────────┐        ┌──────────────────┐
 │  courier client  │──────▶ │  neocourier        │ ─────▶ │  courier client  │
 │  (plugin)        │ signed │  daemon            │  wake  │  (plugin)        │
 └──────────────────┘ envelope│  ├─ append store   │        └────────┬─────────┘
                              │  ├─ verify         │                 │
                              │  ├─ deliver/queue  │        wake → agent turn
                              │  └─ audit log      │
                              └────────────────────┘
```

Deliveries are **at-least-once**, made idempotent by a message id the sender chooses.
A message to a stopped container is **queued, not lost**, and delivered on wake with its
original sent-at time intact — the recipient can see it was delayed, which matters more
than pretending it was instant.

## Implementation language

**Rust**, same rules as the rig: entire backend, Rust Style Guide, warnings denied, `forbid(unsafe_code)`
per crate. The Python validator in this repo is a schema check, not the implementation, and the
workflow that runs it is paused with the rest until the documentation is signed off.

## Status: designed, not implemented

**There is no code in this repository yet** — the schema and the example envelope are the only
machine-readable artefacts here, and both are validated in CI on every push (a valid envelope
must pass, an envelope missing its signature must fail, and an empty example set must not be
reported as success). Every guarantee below — signed envelopes,
at-least-once delivery, wake — is a specification with no implementation and no passing test
beside it. It is written down so the implementation has something to be measured against, and
so the design can be argued with before it is code.

Saying this plainly is deliberate: a documented guarantee with nothing behind it is the same
artefact as a route description that claims an auth posture it does not have, or a monitor that
prints a summary on a clean run. The next push here either ships the envelope plus its tests or
this notice stays where it is.

## Documents

| Doc | What it settles |
|---|---|
| [`docs/protocol.md`](docs/protocol.md) | The envelope, message identity, delivery semantics, ordering, error model |
| [`docs/auth.md`](docs/auth.md) | Per-agent keys, signed envelopes, replay defence, rotation, compromise |
| [`docs/wake.md`](docs/wake.md) | How a message starts a turn: webhook wake, fallback long-poll, offline queue |
| [`docs/transports.md`](docs/transports.md) | HTTP, SSE, unix socket, relay — and when each is correct |
| [`docs/integration-hermes.md`](docs/integration-hermes.md) | Plugin/connector shape, `message_agent` bridge, wake → turn |
| [`docs/operations.md`](docs/operations.md) | Storage, backpressure, loops, metrics, failure modes |
| [`docs/roadmap.md`](docs/roadmap.md) | v0.1 → v1.0, and what is deliberately deferred |

## Status

**Design phase.** This repository is the specification the implementation will be written
against. Nothing here is running in production; the documents say what is settled, what is
provisional, and what is an open question rather than pretending otherwise.

## Licence

Apache License 2.0 — see [`LICENSE`](LICENSE). Contributions are accepted under the same
terms; see [`CONTRIBUTING.md`](CONTRIBUTING.md).

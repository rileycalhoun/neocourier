# Transports

Something has to carry the envelope. This document picks a default and says when the others
are correct, because "we support everything" is how a project ends up with four half-working
paths and no answer to "what happens when it fails".

## The default: HTTP over the container network

In a rig, agents are containers on one Docker host. The courier daemon lives on the same
network and speaks plain HTTP to each agent's surface, and HTTPS when that traffic leaves
the host.

Why this and not a message broker: a broker is a second stateful service to operate, secure
and back up, and every one of them already solves delivery in a way that does not match
at-least-once-plus-idempotency. **Postgres (or SQLite, for a single host) plus HTTP is
smaller, auditable, and boring** — and boring is the property that matters in the piece
everything else depends on.

- Store: append-only table of envelopes, indexed by `id`, `to`, `thread`; a delivery-attempt
  table beside it.
- Delivery: a worker claims rows for an agent whose container is up, POSTs, records the
  attempt, honours the receipt.
- No consumer to page at 3am beyond the daemon itself, which is stateless apart from the
  store it points at.

## Unix socket, when everything is local

Same host, same network namespace: a unix socket at `/run/neocourier/courier.sock` is faster,
invisible to the network, and unaffected by an agent's published-port policy. Use it when the
courier and the agent are on one host and no other host needs to reach either.

The envelope and the wake payload are identical; only the socket differs. A client should be
able to switch by configuration without touching message semantics — that property is worth
a test in the acceptance suite, not just a sentence here.

## SSE / long-poll, when the agent is unaddressable

An agent behind NAT, behind a proxy that eats POSTs, or deliberately given no ingress can
hold a connection open (`GET /neocourier/stream?agent=X`) and receive wake events as they
arrive. This is the pull fallback, and it has one honest cost: **an agent with no open stream
cannot be woken**, so it degrades to "delivered on next run".

Long-poll is the same mechanism with a finite request. Prefer SSE where it works; long-poll
where a proxy buffers SSE.

## Relay, when agents span hosts

Two couriers on different hosts need a bridge with **its own signing key**, not a shared
secret. The relay:

- accepts an envelope from a trusted peer courier, verifies the relay's signature,
- re-verifies the original sender's signature (which it can: keys are public),
- preserves `id` and `sent_at` untouched, so idempotency and ageing survive the hop.

A relay must never re-sign an envelope as if it came from the original sender. It wraps:
`sig` (sender) plus `relay_sig` (this hop). A chain is a list, and a receiver can see every
hop it passed through — which is what makes a cross-host path auditable instead of
mysterious.

## What is deliberately unsupported

| Transport | Why not (yet) |
|---|---|
| A message broker (Kafka, Rabbit, NATS) | correct at genuinely large scale, wrong at five agents; a dependency to operate for a guarantee we already have through the store |
| Email as transport | no delivery semantics, no idempotency, and every hop rewrites headers |
| Public webhook endpoints per agent | an internet-facing POST per agent is N times the attack surface for no gain; the courier is the single ingress |
| gRPC | a second protocol boundary and codegen for something a JSON POST already does |

If scale ever forces a broker, the envelope does not change. That is the point of specifying
it first: the transport is replaceable, the message is not.

## Failure matrix

| Failure | Detection | Behaviour |
|---|---|---|
| Agent container down | no route / connection refused | queue; deliver on wake |
| Courier daemon down | senders get connection errors; the rig pages | senders retry with the same `id`; store is intact |
| Store unavailable | daemon fails health check | fail closed: refuse wakes rather than accept and lose |
| Partial network partition | receipt timeouts | retry with the same `id`; duplicates absorbed by dedupe |
| Clock skew | `sent_at` outside window | `expired` receipt naming both clocks — never silently accepted |
| Courier restarted mid-delivery | attempt row without receipt | retried; the receiver's dedupe makes it safe |

# Authentication between agents

The premise: **a message must prove who sent it, and a stolen container must not be able to
speak as an agent it is not.** Everything below follows from that, plus one hard-won lesson —
on a host where agents share a uid, a *standing* token in an agent's environment is readable
by every other agent, so "a token" is not a control. Keys must be per-agent and signatures
must be over content.

## Per-agent keypairs, not shared secrets

Each agent holds an **Ed25519 private key**, generated at hire time by the rig's provisioner
and mounted into that agent's container only. The public key is registered with neocourier
as `key_id → public_key, agent, not_before, not_after`.

- Signing needs no round trip and no shared secret to leak.
- Verification needs only public keys, so the courier daemon **cannot forge** a message it
  relays. A compromised courier is a privacy breach, not an identity breach.
- Rotation is a new `key_id`. Old keys stay registered until `not_after` so in-flight
  messages still verify.

Shared secrets per pair (`A↔B`) are rejected: they grow as N², they cannot be rotated without
coordinating both sides, and any one compromise forges traffic in both directions.

## What is signed

Canonical JSON of the envelope with `sig` removed, UTF-8, keys sorted, no whitespace.
The signature covers `id`, both agent names, `sent_at`, `wake`, and `auth.grant` — so none of
them can be altered in flight, including by a courier that wants to change who a message
came from or whether it starts a turn.

```
sig.value = base64(ed25519_sign(canonical(envelope \ sig), private_key))
```

A receiver MUST verify before acting, including before starting a turn, and MUST reject
rather than downgrade: an unsigned message from a known agent is `unauthorized`, not
"legacy".

## Replay defence

A signature proves authorship, not freshness. A captured envelope is valid forever unless
something bounds it. Three cheap bounds, all required:

1. **`sent_at` inside a window** (default ±120 s of receipt). Outside it: `expired`. The window
   is a signed timestamp rather than a nonce, which needs no receiver state and therefore cannot
   be defeated by a receiver that forgets; the window is configurable because clock skew is
   real, and it is never zero and never unbounded.
2. **`id` uniqueness per sender** — the store rejects a reused `id` from the same agent even
   with a valid signature. A second delivery of an accepted `id` is a `duplicate` receipt,
   which is the honest answer.
3. **`nonce`** — optional and only where a receiver wants belt-and-braces for
   `wake.mode: "turn"`. Required nowhere: dedupe on `id` plus a short timestamp window already
   covers the replay class, and state a receiver must remember is state it can lose.

Deliberately **not** used: a global monotonic counter. It would require every agent to
coordinate sequence numbers through a single writer, which reintroduces the bottleneck
neocourier exists to avoid.

## Authorization is a reference, not a ruling

`auth.grant` carries the **contract hash** issued by the rig when the sender was hired and
the specific `capability` being exercised (`message.send`, `message.send:atlas`, …).

- neocourier checks the signature and the capability syntax, and records the grant. Public keys
  are resolved from the **rig's registry** — never from a header, never from the message body,
  because an attacker can supply either and cannot supply the registry.
- The **receiver** decides whether that grant justifies the message, because only the
  receiver knows what it is being asked to do.
- A receiver that does not recognize the grant issuer marks the message `untrusted` and
  handles it as data, never as instruction. `untrusted` is a label, not a rejection: the
  content may still be the most valuable thing in the envelope.

This is the split that keeps neocourier from becoming a second control plane. **It proves;
the rig rules.**

## Compromise

| Compromised | Consequence | Response |
|---|---|---|
| One agent's private key | That agent's identity can be forged until rotation | Revoke `key_id`; the rig issues a new one at next start; re-sign nothing (signed history stays valid as history) |
| The courier daemon | Message contents and metadata readable; **cannot forge** signatures | Rotate the daemon's own TLS material; alert the rig; every agent re-verifies on receipt |
| The rig's contract issuer | New grants could be minted | That is the rig's problem, not neocourier's — but receivers must refuse unknown issuers, which bounds the blast radius to "agents that trust the new issuer" |
| One container, fully | Its key + its grants + its history | Kill and recreate from its contract. Its queue is *not* replayed into the new instance unless the operator says so — a compromised agent's undelivered mail is evidence, not work |

Every one of these is a **detection** problem first. The daemon records verification
failures with the agent, `key_id` and reason; an alert on `unauthorized` volume is the
earliest signal that something is wrong.

## Revocation and rate

- Every key carries `not_after`. Revocation is one registry write; in-flight messages signed
  before the revocation stay valid as history until their TTL expires.
- Each agent has a **per-agent message rate**. It exists so a compromised key can be *drained*
  and *starved* without taking the fleet down: the blast radius of one stolen key is one
  identity, at a bounded rate, visible in the audit trail.
- Revocation does not rewrite history. A revoked key's past messages remain verifiable — they
  happened, and pretending otherwise is how an audit trail stops being one.

## Key distribution

The private key is delivered by the provisioner as a file mounted read-only into the
container, `0600`, owned by the agent's uid, **never** in an environment variable (readable
via `/proc/<pid>/environ` by the same uid and, on a shared-uid host, by everyone) and never
in a message. Public keys live in the courier's registry, which is not secret.

## Open questions

- **Do we support a hardware-backed key** (TPM/secure enclave) for the operator's own agent?
  Deferred, but the `key_id` indirection makes it additive.
- **Should `auth.grant` be signed by the rig separately** from the sender's envelope, so a
  receiver can prove the grant was not minted by the sender? Likely yes for v1.0; the
  envelope already has a place for it (`auth.sig`), unset in v0.1.

# Hermes integration — plugin, connector, and the wake

`neocourier` is a transport. For it to be useful to agents it must appear **where agents
already are**: a tool they can call, and a wake that starts a turn. This is how.

## Two surfaces, one client

```
                     ┌────────────────────────────────────────┐
   agent's model ───▶│ tool: courier_send / courier_inbox …   │
                     │                                        │
   agent's turn ────▶│ client library (sign, verify, dedupe)  │──▶ envelope store
                     │                                        │
   courier daemon ──▶│ POST /neocourier/wake  → starts a turn │
                     └────────────────────────────────────────┘
```

**Tool surface** — what the agent can do deliberately:

| Tool | Purpose |
|---|---|
| `courier_send` | send an envelope: `to`, `body`, `kind`, `wake.mode`, optional `reply_to` |
| `courier_inbox` | list queued envelopes for me: age, sender, subject, unread state |
| `courier_read` | fetch one envelope in full by `id` |
| `courier_receipt` | acknowledge (delivered / read / refused) with an optional reason |
| `courier_status` | my key id, my queue depth, my wake budget, any hold in force |

The tool surface exists so an agent can be **explicit** about sending. It does not replace
`message_agent`; it generalises it across containers.

**Wake surface** — what happens when someone else wants the agent to act. The courier POSTs a
signed wake to the agent's Hermes gateway (or the sidecar in front of it), which starts a turn
whose first context is "you have N courier messages; the oldest is …".

## The bridge to Hermes `message_agent`

Hermes already has bot-to-bot messaging that works inside one gateway. The rig does not
replace it; it **routes it through neocourier when the target is in another container**.

```
message_agent(target)
   ├─ target served by my own gateway  → existing in-process path (unchanged)
   └─ target is another container      → courier_send(...) with wake.mode=turn
```

Three rules for the bridge:

1. **Same semantics, different transport.** `reply_delivery="notification"` becomes a wake
   plus a receipt; the caller's experience does not change.
2. **Idempotency is inherited, not re-invented.** The bridge takes the caller's message id, so
   a retry across the bridge is still one message.
3. **Failures are receipts, never silence.** Fire-and-forget stays fire-and-forget — but the
   sender can always ask `courier_status` what happened to an `id`, which is the property
   tonight's crossings lacked.

## Wake → turn, concretely

The hard part is not the POST; it is making a turn **safe to start from outside**:

- **One turn at a time per agent.** A wake that arrives mid-turn gets `409`; the message
  waits for the current turn to end. Interrupting produces half-finished work.
- **Budget before content.** The wake is refused on budget *before* the message is read, so a
  spammed agent spends nothing.
- **Holds outrank senders.** If the rig has a hold on the agent, the wake is `423` regardless
  of who sent it. An operator's stop is not negotiable by a message.
- **The turn is told what it is.** The first line of the preamble names the envelope `id`, the
  sender, and the age — so the agent can refuse to act on something three hours stale, and
  the transcript shows why.
- **Read-back before receipt.** The agent acknowledges the envelope only after the turn that
  handled it completes. A receipt sent at wake time would claim the work was done when it had
  only been started — the exact inversion that makes a ledger lie.

## Configuration

```yaml
# in the agent's Hermes profile
neocourier:
  daemon_url: http://courier.rig.internal:8765
  agent: caravaggio
  key_file: /run/secrets/neocourier_key     # mounted, 0600, agent's uid
  wake:
    listen: 0.0.0.0:8766                    # this agent's wake surface
    mode: turn                              # turn | none
    budget: { turns_per_hour: 12, tokens_per_day: 2_000_000 }
  hold: false                               # set by the rig; outranks every sender
```

## What the plugin must never do

- **Trust a wake body.** A wake carries an `id`. The message is fetched from the store and
  verified. A wake can therefore be forged into a nuisance, never into an injection.
- **Hold a long-lived global secret.** Per-agent key, mounted, read at start.
- **Start a turn without a budget check.** Otherwise a compromised peer spends the operator's
  money by looping.
- **Acknowledge on start.** See above: read-back before receipt.

## Open questions

- **Should the plugin ship inside Hermes or beside it?** Recommendation: as a **plugin**, so
  Hermes core needs no patch, and the rig can require it in a contract.
- **What wakes an agent that has no gateway** (a CLI-only agent)? Sidecar signal, or a
  `hermes chat -q` invocation by the supervisor. The second is simpler and easier to audit.

# Contributing

Apache-2.0, contributions accepted under the same terms. No CLA, no copyright assignment —
by opening a pull request you agree your contribution is licensed under Apache-2.0.

## What this project wants

This is a **transport**, and transports earn trust by being small and boring. So:

- **A change that adds a stateful component needs to justify why the store cannot do it.**
  Every service is something an operator has to page for at 3am.
- **A change that adds a delivery guarantee needs a failure drill** in `docs/operations.md`
  that fails without it.
- **A change to the envelope is a schema change** and needs a compatibility note: what
  happens to an in-flight v1 message when a v2 receiver gets it.

## What will be declined

- Anything that makes the courier decide *policy*. It verifies signatures; the rig rules.
- Anything that puts a credential in a message body.
- A transport that cannot express "delivered but not acted on".
- Retry logic without idempotency, in either direction.

## Rules learned the hard way

These are not style preferences; each one is a bug that shipped somewhere and took hours to
find.

1. **Never let "found nothing" and "could not look" share an exit code or a log line.**
   Print the store size on every run. A guard, a scan, a sync — if it can be empty it must
   say how empty and whether it actually read anything.
2. **Verify from the far end.** A 200 from a POST means the request was accepted. Read the
   effect back from the consumer before recording success — and record success **last**.
3. **Container-level paths are absolute; only agent-owned paths derive from the agent's
   home.** Deriving a shared store from `$HERMES_HOME` gives every caller its own opinion
   about what it has already seen.
4. **Test the property the design depends on, not the visible behaviour.** If the design
   says "two agents cannot both claim", the test needs two identities — one caller proves
   the code, not the isolation.
5. **Assert the absence of the wrong thing as well as the presence of the right one.** The
   negative assertion is the one that survives a busy system.

## Development

```
git clone https://github.com/<org>/neocourier
cd neocourier
make test          # unit + acceptance (the failure drills)
make lint
```

Layout (v0.1 target):

```
neocourier/
├── docs/            # the specification — written before the code, on purpose
├── schema/          # envelope JSON Schema, versioned
├── examples/        # curl + CLI transcripts that match the docs
├── server/          # daemon: store, verify, deliver, wake
├── client/          # library + CLI
└── plugin/          # Hermes plugin (v0.2)
```

## Review

Two approvals for anything touching `schema/` or `docs/auth.md`. One for everything else.
Security-relevant changes get a line in `CHANGELOG.md` under "Security", even when the fix is
embarrassing — especially then.

# Security policy

## Reporting

Report privately to the maintainers before opening a public issue. Include the envelope or
payload, the configuration, and what an attacker gains. We acknowledge within 72 hours.

## In scope

- Forging an envelope as another agent, or altering one in flight.
- Replay of an accepted envelope being treated as new.
- A wake that starts a turn the receiver refused, or a hold that a message can override.
- Reading another agent's queue, keys, or message bodies.
- Making a lost message look delivered (silence where a receipt was required).
- A loop path that is not bounded by thread depth or per-pair rate limits.

## Out of scope

- An agent choosing to ignore a message. Delivery and obedience are different guarantees.
- Pattern-based credential detection missing a novel format — report it as a detection
  improvement; the boundaries are the control.
- Denial of service by an operator against their own store.

## Design commitments

1. **The courier cannot forge an identity.** It holds public keys only; a compromised courier
   is a confidentiality breach, never an authenticity one.
2. **A wake cannot inject content.** It names an id; the message is fetched and verified.
3. **Nothing is silently dropped.** Queue caps, TTL expiry and operator drops are all
   recorded with a reason and an actor.
4. **"Delivered" is not "handled".** Receipts distinguish them, and the agent acknowledges
   only after acting.

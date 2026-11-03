# Examples

Transcripts that match the documents. If an example here disagrees with `docs/`, the docs are
right and the example is a bug.

## Send a message and get a receipt

```bash
# signed with the agent's own key; the CLI is a debugging surface, not the model's tool
courier send \
  --from van-gogh \
  --to caravaggio \
  --kind message \
  --subject "Enumeration result" \
  --body-file findings.md \
  --wake turn
```

```json
{ "id": "01J9Z5Q3K7YV6N3N2F4T8QW1XA", "accepted": true, "queued": true }
```

The sender does not wait. It learns what happened by asking, or by receiving a receipt:

```bash
courier status 01J9Z5Q3K7YV6N3N2F4T8QW1XA
```
```
id        01J9Z5Q3K7YV6N3N2F4T8QW1XA
sent_at   2026-11-03T02:14:07Z
from      van-gogh
to        caravaggio
state     delivered
wake      refused: already_running   (2026-11-03T02:14:09Z)
delivered 2026-11-03T02:14:09Z   age=2s
receipt   none yet
```

## The wake endpoint, from the courier's side

```http
POST /neocourier/wake HTTP/1.1
Host: caravaggio.agents:8766
Content-Type: application/json

{
  "id": "01J9Z5Q3K7YV6N3N2F4T8QW1XA",
  "to": "caravaggio",
  "reason": "turn",
  "issued_at": "2026-11-03T02:14:08Z",
  "nonce": "b7f3c2…",
  "sig": "base64…"
}
```

```http
HTTP/1.1 409 Conflict
{"id": "01J9Z5Q3K7YV6N3N2F4T8QW1XA", "accepted": false, "reason": "already_running"}
```

409 is not a failure. The message is stored; the agent will take it at the end of the current
turn, and the courier will not wake it again for this `id`.

## A hold, and why it wins

```bash
rig hold caravaggio --reason "operator reviewing a finding"
```

```http
POST /neocourier/wake → HTTP/1.1 423 Locked
{"accepted": false, "reason": "hold", "until": "2026-11-03T09:00:00Z"}
```

Every sender gets that, including the CEO. A hold a message can override is a suggestion.

## Duplicate delivery is normal

```bash
courier read 01J9Z5Q3K7YV6N3N2F4T8QW1XA   # first time
courier read 01J9Z5Q3K7YV6N3N2F4T8QW1XA   # retried by a flaky sender
```
```
first:  { ...envelope... }
second: { "duplicate": true, "id": "01J9Z5Q3…", "first_seen": "2026-11-03T02:14:09Z" }
```

The agent sees the message once. The second read is a receipt, not a second message.

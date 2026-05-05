# WhatsApp text round-trip (live, 2026-04-25)

## Send

```bash
curl -sS -X POST http://localhost:8082/api/send \
  -H "Authorization: Bearer df977e70e7d837cd77f74a6690f0c460ba7214a2a22d22339fe743fb9e64ea3e" \
  -H "Content-Type: application/json" \
  -d '{"recipient":"5527988290533","message":"v0.7.0 final regression — please reply briefly."}'
```

Response: `{"success":true,"message":"Message sent to 5527988290533"}`

## Bot reply (verbatim)

> Hi Vini, I searched your emails for "v0.7.0 final regression" but couldn't find any matches. Could you provide more context, or would you like me to search for "v0.7.0" more broadly?

## Verdict

PASS. End-to-end chain confirmed: tester → WhatsApp bridge → backend agent router → Gmail tool invocation (via `gmail_operation` skill) → contextual reply → tester.

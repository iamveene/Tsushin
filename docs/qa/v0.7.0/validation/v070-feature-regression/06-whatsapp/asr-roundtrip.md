# WhatsApp ASR voice-note round-trip (live, 2026-04-25)

## Send

```bash
docker cp backend/tests/fixtures/asr_test_en.ogg \
  tsushin-mcp-tester-...:/tmp/regression-voice.ogg
curl -sS -X POST http://localhost:8082/api/send \
  -H "Authorization: Bearer df977e70e7d837cd77f74a6690f0c460ba7214a2a22d22339fe743fb9e64ea3e" \
  -H "Content-Type: application/json" \
  -d '{"recipient":"5527988290533","media_path":"/tmp/regression-voice.ogg","media_type":"audio"}'
```

Response: `{"success":true,"message":"Message sent to 5527988290533"}`

## Bot reply (verbatim)

> Hello Vini! I've received your test recording for Tsushin Release 0.7. How can I help you with your emails or calendar today?

## Verdict

PASS. End-to-end ASR chain confirmed: tester → bridge (downloaded 19,699-byte ogg) → backend audio_transcript skill (OpenAI ASR provider, default for tenant) → transcribed text "Tsushin Release 0.7" → agent generates contextual reply → bot sends → tester receives. This is the 5th successful ASR round-trip in this session.

---
name: meralion-transcribe
description: Transcribe audio/video to text via the MERaLiON cloud ASR API (api.meralion.ai). Use when the user wants speech-to-text and prefers a cloud service over local whisper (e.g. old/slow machines, or when MERaLiON is the designated transcription provider). Avoids all local GPU/CPU load — audio is uploaded, not processed locally.
agent_created: true
---

# MERaLiON cloud transcription

Transcribe speech-to-text using MERaLiON's hosted ASR. No local model, no local compute — ideal for weak machines (Intel MacBook Air, etc.) or when the user has MERaLiON credits.

## When to use
- User asks to transcribe a recording and MERaLiON is their preferred provider.
- Local whisper/whisper.cpp is explicitly unwanted (slow machine, privacy, or preference).
- Audio is any format ffmpeg can read (m4a, mp3, wav, etc.).

## Credentials (do NOT hardcode)
API key is stored in the **macOS login Keychain**, under the service label `meralion.ai`. Retrieval is by
service label only, so it works on any machine regardless of the Keychain account name:
```bash
MERALION_KEY=$(security find-generic-password -s "meralion.ai" -w)
```
If Keychain retrieval fails, fall back to the `MERALION_KEY` environment variable (user supplies it). Never
write the key to a file or commit it.

**To store / update the key** — service-label only, no account name needed (`-U` updates the matching entry):
```bash
security add-generic-password -s "meralion.ai" -w "PASTE_NEW_KEY_HERE" -U
```
Verify:
```bash
security find-generic-password -s "meralion.ai" -w
```
Inspect metadata only (no secret printed) with `security find-generic-password -s "meralion.ai"` (shows `acct`/`svce`).

## Model / endpoint pitfalls (learned the hard way)
- **Endpoint:** `POST https://api.meralion.ai/v1/audio/transcriptions`
  - The OpenAPI spec at meralion.org:8010 says `/audio/transcription` — that returns **404** on production. Use the `/v1/...` path.
- **Model enum (production):** only `MERaLiON/MERaLiON-3-10B` and `MERaLiON/MERaLiON-3-3B-ASR-CTM` are accepted.
  - The spec's default `MERaLiON/MERaLiON-ASR-EXP` returns **422**. For pure ASR use `MERaLiON-3-3B-ASR-CTM`.
  - ⚠️ **`MERaLiON-3-10B` silently falls back to `3-3B-ASR-CTM` and returns an EMPTY `content` string** (verified 2026-09-12: HTTP 200, `model` field in the response echoes `MERaLiON-3-3B-ASR-CTM`, `choices[0].message.content == ""`, `usage` all zeros). Do not reach for 10B as a "better model" upgrade — it buys nothing. **Always assert the returned text is non-empty before trusting a response.**
- **Auth:** `Authorization: Bearer <KEY>` (also accepts `X-API-Key` header or `?api_key=` query).
- **Body:** JSON `{"audio_url": "data:<mime>;base64,<B64>", ...}` where mime is `audio/wav|audio/mp3|audio/ogg`. Audio must be **16 kHz, mono**.
- **Response:** OpenAI-style — `choices[0].message.content` (fallback to `text` or `transcript`).
- **Errors:** 404 = wrong path; 422 = bad model enum; "Broken pipe" = usually wrong path on a large upload (not size).

## Workflow
1. **Convert to 16 kHz mono** (MP3 keeps the base64 body small; WAV works but is ~4× larger):
   ```bash
   ffmpeg -y -i INPUT -ar 16000 -ac 1 -b:a 64k /tmp/clip.mp3
   ```
2. **POST** (Python stdlib `urllib` — no pip needed; requests works too):
   ```python
   import base64, json, os, urllib.request
   key = os.environ["MERALION_KEY"]
   b64 = base64.b64encode(open("/tmp/clip.mp3","rb").read()).decode()
   body = {"audio_url": "data:audio/mp3;base64,"+b64,
           "model": "MERaLiON/MERaLiON-3-3B-ASR-CTM",
           "return_diarization": True, "return_timestamps": True,
           "boundary_mode": "sequential"}
   req = urllib.request.Request("https://api.meralion.ai/v1/audio/transcriptions",
           data=json.dumps(body).encode(), method="POST")
   req.add_header("Authorization", "Bearer "+key)
   req.add_header("Content-Type", "application/json")
   with urllib.request.urlopen(req, timeout=900) as r:
       j = json.loads(r.read().decode())
   text = j["choices"][0]["message"]["content"]   # or j.get("text")/j.get("transcript")
   ```
3. Long audio (10+ min) is auto-chunked server-side; allow generous timeout.

## Usage limits (ASTAR SG approved tier)
- **Approved tier:** 5 requests/min, 1000 requests/month, **30 hrs audio/month** (~1800 min). This replaces the old 60-min default ceiling — ~30× headroom.
- Check live usage with `GET https://api.meralion.ai/keys/usage` and tier info with `GET /keys/tiers` before a big job.
- **Warn threshold:** only nag when remaining audio budget drops below ~10% (≈3 min) or request budget is nearly exhausted. Do NOT warn on normal files — the 30 hr ceiling absorbs typical jobs.
- **Rate cap:** 5 rpm is a hard limit. Pace batched/chunked jobs (e.g. `sleep 12` between calls) to avoid 429s.

## Noisy audio: repetition-loop degeneration (learned 2026-09-12)
On **noisy multi-speaker** recordings (crowds, restaurants, crosstalk) the 3B model can fall into a
**repetition loop** — it emits hundreds of copies of one token or phrase (observed: "sanitise,
sanitise, sanitise…", "会签合同的话。会签合同的话。…") and the tail of the transcript becomes garbage.
This is a model failure, not a file problem. Single-pass output is NOT trustworthy in that case.

**Remediation recipe — use all three, then triangulate:**
1. **Denoise + high-pass before uploading.** Big quality win:
   ```bash
   ffmpeg -y -i IN -af "highpass=f=85,afftdn=nr=12:nf=-30" -ar 16000 -ac 1 -c:a pcm_s16le out.wav
   ```
   Upload as `data:audio/wav;base64,…` (16 kHz mono, no lossy re-encode).
2. **Chunk into 30–75 s segments** and transcribe each separately. Short windows stop the loop from
   taking over, and the per-chunk `-ss` offset gives you free timestamps. Pacing `sleep 13` between
   calls stays under the 5 rpm cap. Ready-made script: `scripts/chunked_asr.py`.
3. **Triangulate across passes.** Run (a) whole-file, (b) 75 s chunks, (c) 30 s chunks and diff them
   sentence by sentence. **Only content that agrees across passes goes into the deliverable**;
   anything appearing in just one pass gets flagged as uncertain. This is what turns a garbage
   transcript into an honest one.

**Do not silently smooth over ASR garbage.** If a term recurs but is obviously wrong (e.g. "石家庄"
in a wine-tasting talk, where the surrounding description — "world's most famous variety",
green-pepper aroma, fine tannins — is unambiguously Cabernet Sauvignon), reconstruct it *and say it
is a reconstruction with a confidence level*. Also note when the source recording is too degraded
to support a full write-up — a short honest document beats a fluent invented one.

**Verification trick:** cross-check ASR against an independent artifact. Photographed wine labels,
signage, or slides confirm proper nouns that ASR mangles ("十代干白" → 石黛干白; "双目瞳" → 橡木桶;
"李达敏" → 李德美). Always look for a second source of truth before finalising proper nouns.

## Notes
- MERaLiON is pitched at Southeast Asian languages but transcribed Mandarin well in testing.
- Diarization (`return_diarization`) only adds speaker tags for multi-speaker audio; single-speaker talks return plain text.

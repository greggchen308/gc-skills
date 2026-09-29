<p align="center">
  <b>Language / 语言:</b>
  <a href="./README.md">English</a> ·
  <a href="./README.zh-CN.md">简体中文</a>
</p>

# meralion-transcribe

Transcribe audio/video to text via the **MERaLiON cloud ASR API** (`api.meralion.ai`) — a fully hosted
speech-to-text service. No local model, no local GPU/CPU load: your audio is uploaded, never processed on
your machine. Ideal for weak laptops (an old Intel MacBook Air, or any Apple Silicon Mac) or when MERaLiON
is your designated transcription provider.

> **Apple Silicon note.** This skill drives a cloud API, so the *service* works on any Mac. What can break
> is the local toolchain around it. On an arm64 Mac whose `ffmpeg` is still an x86_64 build and where
> **Rosetta 2 is not installed**, `ffmpeg` and every other x86_64 helper fail with
> `Bad CPU type in executable`. The skill documents four arm64-native macOS replacements — `afconvert`,
> `afinfo`, `python3`, `security` — that cover the whole workflow with no `ffmpeg` at all. See
> *No ffmpeg? Apple Silicon fallback* below.

## What It Does

- **Cloud-only transcription** — zero local compute, so it runs fine on old/slow machines.
- **Any input format** — anything `ffmpeg` can read (m4a, mp3, wav, …).
- **OpenAI-style JSON** — `choices[0].message.content`. (Diarization and timestamps are accepted by the API but never surface — see *Notes*.)
- **Noisy-audio toolkit** — a chunked-ASR script to triangulate crosstalk / repetition-loop failures.

## Install

Just tell WorkBuddy:

> Install meralion-transcribe skill from https://github.com/greggchen308/gc-skills/tree/main/meralion-transcribe

Or install manually:

```bash
git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/greggchen308/gc-skills.git
cd gc-skills
git sparse-checkout set meralion-transcribe
mv meralion-transcribe ~/.workbuddy-ai/skills/
```

## Invoke

```
/meralion-transcribe
```

Or just ask WorkBuddy to "transcribe <file> with MERaLiON".

## 1) Get a MERaLiON API Key

1. Open the MERaLiON console: **https://studio.meralion.ai/api-console**
2. Go to the **"My Key"** tab.
3. **Register for free** to create an account and generate your API key.
4. (Alternative) Click **API Tiers → Custom Plan** to request test access.

Keep the key safe — you'll store it in your macOS Keychain (next step) or pass it via the `MERALION_KEY`
environment variable.

## 2) Store the key (macOS Keychain)

```bash
security add-generic-password -s "meralion.ai" -w "PASTE_YOUR_KEY_HERE" -U
```

The skill reads it back at runtime with `security find-generic-password -s "meralion.ai" -w`.

**Non-macOS / quick test:** export the variable instead — the skill falls back to the environment:

```bash
export MERALION_KEY="PASTE_YOUR_KEY_HERE"
```

Never write the key to a file or commit it.

## How It Works

1. **Convert to 16 kHz mono** with `ffmpeg` (MP3 keeps the upload small; WAV works but is ~4× larger).
2. **POST** the base64 audio to `https://api.meralion.ai/v1/audio/transcriptions` with `Authorization: Bearer <KEY>`.
3. The server auto-chunks long audio (10+ min); allow a generous timeout.
4. **Chunked pass (recommended for long/noisy audio):** run `scripts/chunked_asr.py` alongside the whole-file
   pass and triangulate — see below.

```bash
# denoise + high-pass, then 16 kHz mono WAV
ffmpeg -y -i IN -af "highpass=f=85,afftdn=nr=12:nf=-30" -ar 16000 -ac 1 -c:a pcm_s16le out.wav
# chunked pass: SRC DENOISED_WAV CHUNK_SECONDS [OUTDIR]
python3 scripts/chunked_asr.py IN out.wav 60 /tmp/meralion_asr
```

## No ffmpeg? Apple Silicon fallback

The skill normally shells out to `ffmpeg`. On a Mac where `ffmpeg` is an x86_64 build and **Rosetta 2 is
not installed**, it dies with `Bad CPU type in executable` — and so does every other x86_64 helper. Four
macOS tools are arm64-native and cover the whole workflow:

| Need | Broken | Native replacement |
|---|---|---|
| Audio → 16 kHz mono WAV | `ffmpeg` (x86_64) | **`/usr/bin/afconvert`** |
| Duration / source params | `ffprobe` (x86_64) | **`/usr/bin/afinfo`** |
| HTTPS POST + JSON | x86_64 Python | **`/usr/bin/python3`** (universal) |
| Keychain key | — | `/usr/bin/security` |

```bash
# 16 kHz mono 16-bit WAV — no ffmpeg. afconvert ships with every macOS.
/usr/bin/afconvert -f WAVE -d LEI16@16000 -c 1 IN.m4a /tmp/out.wav
# ALWAYS confirm the duration matches the source before uploading
/usr/bin/afinfo /tmp/out.wav | grep duration
```

**`afconvert` has no MP3 encoder**, so on such a machine WAV is the only output format — the "MP3 keeps the
upload small" advice above does not apply. Slice chunks in Python with the stdlib `wave` module instead of
`ffmpeg -ss`. Ready-made harness: `scripts/test_meralion.py`.

**Call real binaries by absolute path** (`/bin/ls`, `/usr/bin/tail`, `/usr/bin/curl`). Bare names may hit a
shim that execs the wrong architecture.

## Long Files: Silent Omission (read this)

A single whole-file request on a long recording can return **HTTP 200, a non-empty `content` string, sane
`usage` — and still be missing a large fraction of the audio.** Observed on a 910 s (15 min) two-part
recording (talk + audience Q&A): the whole-file pass returned 4,298 chars and covered the talk, but
**dropped roughly half the Q&A** with no error, no repetition loop, and no warning sign. The chunked passes
returned ~5,000 chars over the same audio and covered the whole session.

This is **worse than the repetition loop**, because a repetition loop is visibly broken while silent
omission looks like success. A short transcript is the only tell, and "short" is hard to judge without a
baseline.

**Rule: never trust a single whole-file pass on anything longer than ~5 minutes.** Always also run the
chunked pass and compare (a) total character count and (b) whether the tail of the session is present.
A defensible rule of thumb for Mandarin speech: expect roughly **250–350 characters per minute** of
continuous speech; a whole-file transcript far below that is suspect, not terse.

Cheap check — count characters and look at the tail:
```bash
python3 -c "t=open('asr_whole.txt').read(); print(len(t)); print(t[-800:])"
```

**Practical consequence — but judge the audio first.** For **noisy / crowded / very long** audio, treat the
*chunked* pass as the primary transcript and the whole-file pass as a coherence cross-check. **Counter-case:**
on **clean close-mic** audio the whole-file pass can be *better* — measured on a 526 s Mandarin room
recording, whole-file **2,581** chars vs chunked **2,091**, with chunk boundaries introducing reduplicated
syllables ("减减少") and mid-sentence cuts. Run both passes either way; keep the one that reads most coherently.

## Models & Endpoint Notes (hard-won)

- **Endpoint:** `POST https://api.meralion.ai/v1/audio/transcriptions`. The OpenAPI spec's `/audio/transcription` returns **404** on production — use the `/v1/...` path.
- **Model:** use `MERaLiON/MERaLiON-3-3B-ASR-CTM`. The spec default `MERaLiON/MERaLiON-ASR-EXP` returns **422**; `MERaLiON-3-10B` **silently falls back to the 3B** — the response `model` field echoes `MERaLiON-3-3B-ASR-CTM` with no error, so requesting 10B buys nothing. Always assert the returned text is non-empty *and* check for an `error` key: a valid zero-sample WAV returns **HTTP 200 carrying `code: 400`** in the body, so a status-code check alone sees a rejected request as success.
- **Auth:** `Authorization: Bearer <KEY>` (also accepts `X-API-Key` or `?api_key=`).
- **Body:** `{"audio_url":"data:<mime>;base64,<B64>"}`, where mime is `audio/wav|audio/mp3|audio/ogg`. Audio must be **16 kHz, mono**.
- **Response:** OpenAI-style — `choices[0].message.content` (fallback to `text` or `transcript`).
- **Errors:** 404 = wrong path; 422 = bad model enum; "Broken pipe" = usually wrong path on a large upload.

## Usage Limits (ASTAR SG approved tier)

- **Approved tier:** 5 requests/min, 1000 requests/month, **30 hrs audio/month** (~1800 min) — far above the old 60-min default.
- Check live usage with `GET https://api.meralion.ai/keys/usage`; tier info with `GET /keys/tiers`.
- **Rate cap:** 5 rpm is a hard limit. Pace batched/chunked jobs (`sleep 12–13` between calls) to avoid 429s.

## Noisy Audio: Repetition-Loop Fix

On noisy multi-speaker recordings (crowds, restaurants, crosstalk) the 3B model can fall into a
**repetition loop** — hundreds of copies of one phrase — and the tail of the transcript becomes garbage.
This is a model failure, not a file problem.

**Remediation (use all three, then triangulate):**

1. **Denoise + high-pass before uploading** (see the command in *How It Works* above).
2. **Chunk into 30–75 s segments** and transcribe each (script: `scripts/chunked_asr.py`); the per-chunk offset gives free timestamps.
3. **Triangulate across passes by SEMANTIC ANCHORS — never by diffing text.** The model returns a *paraphrase*, not a copy: re-running the same 75 s yields the same meaning in different characters. Measured 12-gram overlap between whole-file and chunked passes is only **~55 % (Cantonese) / ~72 % (Mandarin)** even when character counts agree within 0.4 %. A text diff therefore reports massive "divergence" when nothing was omitted, and a keep-only-what-agrees rule would discard almost everything. Instead, compare **numbers, dates, Latin-script words and proper nouns** across passes: anything present in one and absent from the other is a genuine omission/error candidate, while wording differences around a shared anchor are non-determinism. Keep the pass that reads most coherently and log the other's unique anchors as uncertainties.

Do not silently smooth over ASR garbage. If a term recurs but is obviously wrong, reconstruct it *and say so* with a confidence level. A short honest document beats a fluent invented one.

## Verify Names Before You "Fix" Them

A confident-looking correction can itself be the error — and it is **harder** to catch than a garbled
transcript, because it reads plausibly. **Before "fixing" an ASR'd product or brand name, search the raw
string exactly as heard.**

Real case: a transcript said "MiniMax H3". Because the speaker was talking about voices, this was
reconstructed as a mis-transcription of MiniMax's `speech-2.6-hd` speech model, and published as such. The
raw string was **correct** — MiniMax H3 is a real product (their omni-modal video model). The speaker was
comparing video-generation options, not TTS. One search of the literal name would have caught it.

**Rule: if the as-heard string resolves to a real product, keep it.** Only reconstruct when it resolves to
nothing. And be suspicious of any reconstruction that requires the speaker to have been in the domain you
had already assumed they were in.

## Files

- `SKILL.md` — full trigger conditions, endpoint/model pitfalls, limits, and the remediation recipe.
- `scripts/chunked_asr.py` — segmented transcription for triangulation of noisy / long audio.
  Usage: `python3 chunked_asr.py SRC DENOISED_WAV CHUNK_SECONDS [OUTDIR]`.
- `scripts/test_meralion.py` — end-to-end smoke test using only native macOS tools (no `ffmpeg`, no pip).
  Usage: `/usr/bin/python3 scripts/test_meralion.py AUDIO [CHUNK_SECONDS]`.
- `CHANGELOG.md` — dated revision history for this skill.

## Notes

- MERaLiON is pitched at Southeast Asian languages but transcribed Mandarin and Hong Kong Cantonese well in
  testing. No evidence on telephony, heavy background noise, overlapping speakers, or the SEA languages it
  targets — do not generalise from conference-room recordings. Mandarin quality > Cantonese quality.
- **Diarization and timestamps do not work.** `return_diarization` / `return_timestamps` are accepted but
  never surface in the response — the schema carries no speaker labels and no segment timings. Derive
  timestamps from your own chunk `-ss` offsets. Do not promise diarization to a user.
- **Cantonese output script is wrong by default** — the model returns Cantonese vocabulary in mixed
  Simplified/Traditional orthography (measured **24 % Simplified-only** CJK in a transcript that must be
  Traditional). It needs an `s2hk` pass; the conversion recipe lives in the `dashscope-qwen-asr` skill.
- **Proper nouns are the single biggest weakness**, in both languages — an organisation's own name came back
  as six different strings across passes. Cross-check against an independent artifact (photo, slide, website).
- Normally requires `ffmpeg`/`ffprobe` on `PATH` and Python 3 (for the scripts). On an Apple Silicon Mac
  without Rosetta 2, use the native fallback above instead — no `ffmpeg` required.

## License

Provided as-is for personal and educational use. Add a LICENSE to this repository if you plan to redistribute.

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

## ⚠️ FIRST: check the toolchain actually runs (arm64 Mac + no Rosetta = every helper broken)
Verified 2026-09-29 on an **Apple M5, macOS 27.0.1**. After a machine migration every WorkBuddy-managed
runtime was still **x86_64** while the machine is **arm64**, and **Rosetta 2 was not installed** — so
`ffmpeg`, the managed Python and the managed Node all die with `Bad CPU type in executable`. The bash
sandbox's brokered shims (`ls`, `mkdir`, `head`, `cat`, `tail`, …) fail too, because they exec
`$CODEBUDDY_NODE_BIN`, which points at the x86_64 Node.

**The MERaLiON API is unaffected — it is a cloud service.** Only the local driver breaks. Four
system tools are arm64-native and cover the entire workflow:

| Need | Broken | Native replacement |
|---|---|---|
| Audio → 16 kHz mono WAV | `ffmpeg` (x86_64) | **`/usr/bin/afconvert`** |
| Duration / source params | `ffprobe` (x86_64) | **`/usr/bin/afinfo`** |
| HTTPS POST + JSON | managed venv python | **`/usr/bin/python3`** (3.8.2, universal) |
| Keychain key | — | `/usr/bin/security` |

```bash
# 16 kHz mono 16-bit WAV, no ffmpeg. afconvert is native on every macOS.
/usr/bin/afconvert -f WAVE -d LEI16@16000 -c 1 IN.m4a /tmp/out.wav
# ALWAYS confirm duration matches the source before uploading
/usr/bin/afinfo /tmp/out.wav | /usr/bin/grep duration
```

**Call real binaries by ABSOLUTE PATH** (`/bin/ls`, `/usr/bin/tail`, `/usr/bin/curl`). A bare name hits
the broken shim and returns exit 126. `/usr/local/bin/node` (v24.14.0) is universal and *does* run
natively if Node is genuinely needed.

**`afconvert` has NO MP3 encoder** — `mp3` appears only as an *input* container format. On a
broken-toolchain machine you cannot produce the small MP3 bodies the main recipe recommends, so
**upload WAV**. Chunk-slicing is then done in Python, not ffmpeg (stdlib `wave`: `setpos()` +
`readframes()`) — ready-made harness at `scripts/test_meralion.py`.

**Measured end-to-end on that machine:** 253 s m4a → `afconvert` WAV → **10.81 MB base64 body →
HTTP 200 in 5.0 s, 1,628 chars**, no omission. The whole path works with zero x86_64 binaries.

## Credentials (do NOT hardcode)
API key is stored in the **macOS login Keychain**, under the service label `meralion.ai`. Retrieval is by
service label only, so it works on any machine regardless of the Keychain account name:
```bash
MERALION_KEY=$(security find-generic-password -s "meralion.ai" -w)
```
If Keychain retrieval fails, fall back to env var `MERALION_KEY` (user supplies it). Never write the key to a file or commit it.

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
  - ⚠️ **`MERaLiON-3-10B` silently falls back to `3-3B-ASR-CTM`** — the response `model` field echoes
    `MERaLiON/MERaLiON-3-3B-ASR-CTM` with no error. Re-verified 2026-09-29, 3/3. Do not reach for 10B as
    a "better model" upgrade — it buys nothing. **Always assert the returned text is non-empty before
    trusting a response.** (The 2026-09-12 note also recorded an empty `content`; that half did **not**
    reproduce on 2026-09-29 — see "API contract gotchas". Do not cite empty content as current.)
- **Auth:** `Authorization: Bearer <KEY>` (also accepts `X-API-Key` header or `?api_key=` query).
- **Body:** JSON `{"audio_url": "data:<mime>;base64,<B64>", ...}` where mime is `audio/wav|audio/mp3|audio/ogg`. Audio must be **16 kHz, mono**.
- **Response:** OpenAI-style — `choices[0].message.content` (fallback to `text` or `transcript`).
- **Errors:** 404 = wrong path; 422 = bad model enum; "Broken pipe" = usually wrong path on a large upload (not size).

## Long files: whole-file passes silently OMIT content (learned 2026-09-19)
A single whole-file request on a long recording can return **HTTP 200, a non-empty `content` string, sane
`usage` — and still be missing a large fraction of the audio.** Observed on a 910 s (15 min) two-part
recording (talk + audience Q&A): the whole-file pass returned 4,298 chars and covered the talk, but
**dropped roughly half the Q&A with no error, no repetition loop, and no warning sign.** The chunked
passes returned ~5,000 chars over the same audio and covered the whole session.

**This is worse than the repetition loop**, because a repetition loop is visibly broken while silent
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

**Practical consequence:** for long files, treat the *chunked* pass as the primary transcript and the
whole-file pass as a coherence cross-check — not the reverse.

### ⚠️ Very long files: the whole-file pass can be impossible — split it in half (learned 2026-09-24)
On a **3,377 s (56 min)** English room recording, the whole-file pass **failed outright**:

| Attempt | Body size | Result |
|---|---|---|
| Whole file, 48 kbps mono MP3 | **27.0 MB base64** | **HTTP 400 Bad Request**, empty body |
| Two halves (~28 min each), 24 kbps mono MP3 | 6.76 / 6.75 MB base64 | **HTTP 200**, 25,889 + 24,908 chars |

The 400 came back in ~26 s with no diagnostic detail. **Treat a large base64 body as a hard limit
somewhere between 7 MB and 27 MB** — do not assume "auto-chunked server-side" means "any size works".
**Narrowed 2026-09-29: a 10.81 MB base64 body (253 s, 16 kHz mono WAV, 8.11 MB raw) returned HTTP 200
in 5.0 s.** So the ceiling sits between **10.81 MB and 27 MB**, not between 7 and 27 — a 10.8 MB body is
safe. Small sample: stay conservative above ~11 MB and prefer the half-file split for anything long.

**Recipe for files over ~30 min** — replace the whole-file cross-check with a **half-file pair**:
```bash
# split at the midpoint, drop to 24 kbps (16 kHz mono) to keep the body small
ffmpeg -y -v error -ss 0    -t 1690 -i clean.wav -ar 16000 -ac 1 -b:a 24k half0.mp3
ffmpeg -y -v error -ss 1690 -t 1687 -i clean.wav -ar 16000 -ac 1 -b:a 24k half1.mp3
```
Two requests, ~14 MB total, and the pair still gives you the two things the cross-check exists for:
a **total character count** to compare against the chunked pass, and a **tail** to confirm the end of
the session is present. Concatenate the halves before comparing anchors.

**Wall-clock cost of a long chunked pass.** 46 × 75 s chunks took **13 min 27 s** (~17.5 s/chunk) —
the 5 rpm cap plus request latency, not the `sleep 13` alone. Budget ~15 min for a 56-min file, and
note that piping the script to `tail` **buffers all output until it finishes** — to watch progress,
poll the count of `*_part*.wav` files in the outdir instead.

**Validated outcome on that file:** chunked 50,337 chars vs whole 50,797 chars — a **0.9 % delta**,
both tails resolving at the same sentence. Anchor comparison showed heavy paraphrase (e.g. the chunked
pass rendered "Ellen" as "Alex", "Facebook" as "TikTok", "Claude" as "Klaus", "TikHub-ish API" as
"Jingup"), which is **non-determinism, not omission** — but it is exactly why proper nouns must be
cross-checked against photos, never trusted from a single pass.

### ⚠️ Counter-case (2026-09-22): on clean close-mic audio the whole-file pass was BETTER
Two Jan-2026 Hong Kong event recordings — 253 s Cantonese panel, 526 s Mandarin Q&A, both conference
rooms with close mics, denoised per the recipe above — came out the other way round:

| | whole-file | chunked (75 s) |
|---|---|---|
| Cantonese | 1,580 chars | 1,587 chars (+0.4%) |
| Mandarin | **2,581 chars** | 2,091 chars (**23% shorter**) |
| Coherence | clean ending ("…谢谢。") | mid-sentence chunk boundaries; "KPI" and "部門" dropped in one chunk |

Chunk boundaries also *introduced* errors — reduplicated syllables at stitch points ("减减少",
"很很glad") — and truncated mid-sentence. The chunked pass was strictly worse on both files.

**Revised rule:** the omission failure needs **noisy, crowded, long** audio to trigger. Judge before
choosing:
- **Clean close-mic audio, either language → run both, but treat the WHOLE-FILE pass as primary** and
  use chunked as the cross-check. Check the tail for a natural ending.
- **Noisy / crowd / crosstalk / very long → the 2026-09-19 rule stands: chunked is primary.**

Either way, run both. The cheap discriminator is still (a) character count and (b) whether the tail
resolves. Do not apply the chunked-is-primary rule mechanically.

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
3. **Triangulate across passes — by SEMANTIC anchors, not by diffing text.**
   ⚠️ **Corrected 2026-09-22: "diff them sentence by sentence, keep only what agrees" does NOT work
   with this model.** On clean audio the model returns a *paraphrase*, not a copy: re-running the same
   75 s of audio gives the same meaning in different characters. Measured 12-gram overlap between
   whole-file and chunked passes was only **~55%** (Cantonese) and **~72%** (Mandarin) — despite
   character counts matching within 0.4%. A text diff therefore reports massive "divergence" when
   nothing has been omitted, and the keep-only-what-agrees rule would discard almost everything.

   **What to do instead** — compare *factual anchors*, which are stable across passes:
   - extract numbers, dates, Latin-script words and proper nouns from each pass and compare the sets;
   - anything present in one pass and absent in the other is a genuine candidate for omission or error;
   - differences in wording around a shared anchor are non-determinism, not signal — ignore them;
   - spot-check the tail of each pass and the total character count.
   Keep the pass that reads most coherently as the primary; log the other's unique anchors as
   uncertainties. This is what turns a garbage transcript into an honest one.

**Do not silently smooth over ASR garbage.** If a term recurs but is obviously wrong (e.g. "石家庄"
in a wine-tasting talk, where the surrounding description — "world's most famous variety",
green-pepper aroma, fine tannins — is unambiguously Cabernet Sauvignon), reconstruct it *and say it
is a reconstruction with a confidence level*. Also note when the source recording is too degraded
to support a full write-up — a short honest document beats a fluent invented one.

**Verification trick:** cross-check ASR against an independent artifact. Photographed wine labels,
signage, or slides confirm proper nouns that ASR mangles ("十代干白" → 石黛干白; "双目瞳" → 橡木桶;
"李达敏" → 李德美). Always look for a second source of truth before finalising proper nouns.

**Corollary — do NOT normalise an unfamiliar name into a familiar one (learned 2026-09-19).** A
confident-looking correction can itself be the error, and it is harder to catch than a garbled transcript
because it reads plausibly. **Before "fixing" an ASR'd product or brand name, search the raw string exactly
as heard.**

Real case: a transcript said "MiniMax H3". Because the speaker was talking about voices, this was
reconstructed as a mis-transcription of MiniMax's `speech-2.6-hd` speech model, and published as such. The
raw string was **correct** — MiniMax H3 is a real product (their omni-modal video model). The speaker was
comparing video-generation options, not TTS. One search of the literal name would have caught it.

Rule: **if the as-heard string resolves to a real product, keep it.** Only reconstruct when it resolves to
nothing. And be suspicious of any reconstruction that requires the speaker to have been in the domain you
had already assumed they were in.

## API contract gotchas (re-verified 2026-09-29 — two of the 2026-09-22 claims had changed)

**`return_diarization` and `return_timestamps` do NOT surface in the response.** Re-tested 2026-09-29
on a multi-speaker 75 s chunk with both set to `true`: full schema is
`id, object, created, model, choices, usage`; choice = `index, message, finish_reason`; message =
`{role, content}` — **no speaker labels, no segment timings, no field that could carry either**.
Unchanged. Do not promise diarization to a user. Derive timestamps from your own chunk `-ss` offsets.

**Empty audio: the behaviour CHANGED between 22 and 29 September 2026.** Three cases, all tested
2026-09-29 — treat them separately:

| Input | HTTP | Body |
|---|---|---|
| 0.05 s of digital silence | 200 | `content: "(nospeech)\n"` — an explicit sentinel |
| Valid zero-sample WAV (78-byte header, data size 0) | **200** | `{"error":{…,"type":"BadRequestError","code":400}}` |
| Malformed 78-byte header (data chunk declares 2,400,000 bytes, file is 78) | 500 | `Internal Server Error`, plain text |

The `(nospeech)` sentinel is the fix that was asked for — a batching caller can now detect a silent
segment instead of silently losing it. **But the zero-sample case returns HTTP 200 carrying a
`code: 400`**, so a caller checking only `response.status_code` still treats a rejected request as a
successful empty transcription. **Keep asserting non-empty output *and* check for an `error` key** —
a status-code check alone is not sufficient.

**`MERaLiON-3-10B` silently falls back to `3-3B-ASR-CTM`.** Re-tested 2026-09-29, 3/3: the response
`model` field echoes `MERaLiON/MERaLiON-3-3B-ASR-CTM` when 10B was requested, with no error and no
notice. **But the "EMPTY `content`" half did NOT reproduce — 3/3 returned real text.** The empty
content was a 2026-09-12 observation that the 2026-09-22 evaluation inherited without re-hitting it.
So: the silent fallback is real and stable; the empty content is not. Never reach for 10B as an
upgrade — use `MERaLiON/MERaLiON-3-3B-ASR-CTM` — but do not assert empty content as current behaviour.

**⚠️ Two different response schemas are in circulation on the same endpoint (2026-09-29).**
`id: "chunked_transcription_…"` returns the minimal schema above. `id: "chatcmpl-…"` returns a full
OpenAI-style shape — top level adds `service_tier, system_fingerprint, prompt_logprobs,
prompt_token_ids, kv_transfer_params`; choice adds `logprobs, stop_reason, token_ids`; message adds
`refusal, annotations, audio, function_call, tool_calls, reasoning`. In a 5-request sample the split
correlated with request size (2.4 MB bodies → minimal; 1.7 KB body → full), but that is **not
distinguishable from load-balancing across two deployments** at n=5. Consequence either way: do not
assume field presence. Parse defensively, and if a finding about API behaviour refuses to reproduce,
suspect you are talking to the other backend.

## ⚠️ Verify your local audio duration before chunking (learned 2026-09-22)
A killed `ffmpeg` left a denoised WAV of **434 s for a 526 s source**. The chunked pass then covered
only the first 434 s — and **every chunk returned HTTP 200 with plausible text**. Nothing in the API
response indicated a gap. The whole session's tail was silently absent from the chunked transcript.

Two defences, both cheap:
```bash
# 1. confirm the converted file matches the source
ffprobe -v error -show_entries format=duration -of csv=p=0 SOURCE
ffprobe -v error -show_entries format=duration -of csv=p=0 converted.wav
# 2. check the chunked pass is not SHORTER than the whole-file pass
```
**Symptom to recognise:** chunked total < whole-file total. That asymmetry is the tell.
Also note: a long `ffmpeg` chain can be killed mid-write and still leave a *playable-looking* file —
check duration, not just existence.

## Cantonese output: script is WRONG by default (learned 2026-09-22)
On Hong Kong Cantonese the model returns **Cantonese vocabulary in mixed Simplified/Traditional
script**. Measured: **265 of 1,096 CJK characters (24%) were Simplified forms** in a transcript that
must be Traditional (个, 样, 讲, 点, 实, 为, 对, 过, 机, 会, 边, 击, 经). It does get Cantonese-specific
characters right (嘅, 咁, 嗰, 嚟, 唔, 係, 哋, 咗) — it is the *orthography* that is wrong, not the
variety. Mandarin output is correctly Simplified and needs **no** conversion.

**Do not re-derive the conversion recipe here — it is language-level, not vendor-level, and already
written up in full in the `dashscope-qwen-asr` skill** (section "Script handling: choose traditional
vs simplified by detected language"). Read it before normalising; it covers the `s2hk` invocation,
the copula traps, the 系統/系列/體系 and 聯繫/維繫 shielding lists, the length-preservation assert,
and the rule that proper-noun fixes run *after* conversion.

Three points specific to MERaLiON output:

- The same `s2hk` copula trap applies: MERaLiON's `系`/`係` is inconsistent, and a naive `s2hk` pass
  turns some copulas into **繫** ("已經繫好難") — the wrong character, which reads plausibly and is
  therefore hard to catch. Verify after converting.
- `s2hk` also normalises the Cantonese demonstrative `𠮶` → `嗰`. Both are valid HK forms; accept it and
  say so in the deliverable. `𠮶` is not an error to "fix" back.
- The model's own `嘅`/`嗰`/`咗` are correct and must **not** be "corrected" — only the Simplified
  orthography needs converting. Script conversion must never be cover for rewording.

## Performance (measured 2026-09-22)
- **Latency is excellent and length-insensitive:** 253 s → **4.2 s** (~60× realtime); 526 s → **5.0 s**
  (~105× realtime); median across 15 requests **2.7 s**. A 15-min talk transcribes in ~5 s.
- **The 5 rpm cap is the binding constraint, not throughput or cost.** A 15-request triangulated job
  spends ~3 min of wall clock in `sleep`. Quota is a non-issue: 13 min of audio cost ~20 audio-minutes
  against a 30 hr/month allowance. Multi-pass triangulation costs only ~2.3× the audio.
- **Repetition-loop degeneration did NOT recur** on two noisy multi-speaker event recordings (15
  requests). The 2026-09-12 failure mode appears to have been addressed — but keep the recipe in
  reserve rather than assuming it is gone.

## Notes
- MERaLiON is pitched at Southeast Asian languages but transcribes Mandarin and Hong Kong Cantonese
  well in testing. No evidence gathered on telephony, heavy background noise, overlapping speakers, or
  the SEA languages it targets — do not generalise from conference-room recordings.
- **Mandarin quality > Cantonese quality**, but both are usable. Mandarin numbers/dates/code-switching
  were clean first try; Cantonese-accented English homophones are the weakest layer
  (observed: Victor/Vicky, password/passport, co-relate/correlate, compromised/compromise).
- **Proper nouns and acronyms are the single biggest weakness, in both languages.** An organisation's
  own name came back as six different strings across passes ("Kong Kong Kai", "HKAI", "康康盖",
  "香港G", "香港盖", "蜂蜂盖"); a product name as six more. Unrecoverable without external knowledge.
  A hotword/custom-vocabulary parameter would fix this class outright — ask for one.
- Diarization is documented but does not work (see API gotchas). Do not rely on it.

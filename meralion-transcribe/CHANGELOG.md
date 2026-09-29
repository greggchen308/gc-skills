# Changelog

All notable changes to the `meralion-transcribe` skill are documented here.

## 2026-09-29
- **NEW: Apple Silicon / arm64 coverage.** Added a "check the toolchain actually runs" section. On an arm64
  Mac whose helpers are still x86_64 builds and where **Rosetta 2 is not installed**, `ffmpeg` and the
  managed Python/Node all fail with `Bad CPU type in executable`. Documented four arm64-native system
  replacements covering the whole workflow — `/usr/bin/afconvert` (audio → 16 kHz mono WAV),
  `/usr/bin/afinfo` (duration), `/usr/bin/python3` (HTTPS POST), `/usr/bin/security` (Keychain) — plus the
  rule to call real binaries by absolute path. Note `afconvert` has **no MP3 encoder**, so WAV is the only
  output format available on such a machine.
- **NEW script: `scripts/test_meralion.py`** — end-to-end harness using native tools only (convert →
  duration check → whole-file pass → optional chunked cross-check → char-count delta).
- **CORRECTED (changed upstream): empty audio no longer returns silent success.** 0.05 s of digital silence
  now returns `content: "(nospeech)"`. But a **valid zero-sample WAV returns HTTP 200 carrying `code: 400`**
  in the body — a status-code check alone still treats a rejected request as success. Assert non-empty
  output *and* check for an `error` key.
- **CORRECTED (stale claim): `MERaLiON-3-10B` does not return empty content.** The silent fallback to
  `3-3B-ASR-CTM` reproduces 3/3, but all three attempts returned real text. Keep the fallback warning; drop
  the empty-content claim.
- **NEW: two response schemas on the same endpoint.** `id: chunked_transcription_…` (minimal) vs
  `id: chatcmpl-…` (full OpenAI-style). Parse defensively — do not assume field presence. If an
  API-behaviour finding refuses to reproduce, suspect you are talking to the other backend.
- **DATA POINT: base64 body ceiling narrowed to between 10.81 MB and 27 MB** (a 10.81 MB body returned
  HTTP 200 in 5.0 s), previously recorded as "7–27 MB".

## 2026-09-22
- **CORRECTED (the method itself was wrong): do not triangulate by diffing text.** The model returns a
  *paraphrase*, not a copy — measured 12-gram overlap between whole-file and chunked passes is only
  **~55 % (Cantonese) / ~72 % (Mandarin)** even when character counts agree within 0.4 %. The previous
  "diff sentence by sentence, keep only what agrees" rule reports massive divergence where nothing was
  omitted, and would discard almost everything. Replaced with **semantic-anchor comparison**: compare
  numbers, dates, Latin-script words and proper nouns across passes; wording differences around a shared
  anchor are non-determinism, not signal.
- **CORRECTED: the chunked pass is not always primary.** On clean close-mic audio the whole-file pass was
  *better* (526 s Mandarin: 2,581 vs 2,091 chars, with chunk boundaries introducing reduplicated syllables
  and mid-sentence cuts). The omission failure needs noisy/crowded/long audio. Judge before choosing; run
  both passes either way.
- **CORRECTED: diarization and timestamps do not work.** `return_diarization` / `return_timestamps` are
  accepted but never surface — the response schema carries no speaker labels and no segment timings.
  Derive timestamps from your own chunk `-ss` offsets. Do not promise diarization to a user.
- **NEW: verify local audio duration before chunking.** A killed `ffmpeg` left a 434 s WAV for a 526 s
  source, and every chunk still returned HTTP 200 with plausible text — the session tail was silently
  absent. Compare durations, and treat "chunked total < whole-file total" as the tell.
- **NEW: Cantonese output script is wrong by default.** The model returns Cantonese vocabulary in mixed
  Simplified/Traditional orthography (measured 24 % Simplified-only CJK). Needs an `s2hk` pass; the
  conversion recipe lives in the `dashscope-qwen-asr` skill.
- **NEW: performance measurements.** Latency is length-insensitive (253 s → 4.2 s; 526 s → 5.0 s; median
  2.7 s). The 5 rpm cap, not throughput, is the binding constraint.
- **`scripts/chunked_asr.py` hardened**: duration verified against the source before chunking, zero-length
  results reported as failures rather than silence, sub-1.5 s chunks skipped.

## 2026-09-19
- **Hardening: silent omission on long files.** A single whole-file pass on recordings longer than ~5 min
  can return HTTP 200 with a non-empty `content` and sane `usage`, yet silently drop a large fraction of
  the audio (observed: ~half of a 15-min talk + Q&A dropped, no error, no repetition loop). Added the rule:
  never trust a single whole-file pass beyond ~5 min — always also run the chunked pass and compare (a)
  total character count and (b) whether the tail of the session is present. Treat the chunked pass as the
  primary transcript. Added a ~250–350 chars/min baseline for Mandarin continuous speech and a cheap
  character-count + tail sanity check.
- **Fix: do not normalise an unfamiliar name into a familiar one.** A confident reconstruction can itself
  be the error (harder to catch than garbled text because it reads plausibly). Before "fixing" an ASR'd
  product / brand name, search the raw string exactly as heard; keep it if it resolves to a real product.
  Real case: "MiniMax H3" was wrongly rewritten to a TTS model — H3 is a real omni-modal video model.
- **script: `chunked_asr.py` signature changed** to `SRC DENOISED_WAV CHUNK_SECONDS [OUTDIR]`; output now
  lands in a caller-supplied OUTDIR (default `/tmp/meralion_asr`).

## 2026-09-16
- Initial publish: cloud ASR transcription skill, EN / 简体中文 READMEs, and the chunked triangulation
  script.

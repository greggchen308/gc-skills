# Changelog

All notable changes to the `meralion-transcribe` skill are documented here.

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

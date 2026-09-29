#!/usr/bin/env python3
"""Chunked transcription on a denoised WAV, to cross-check a whole-file pass.

Usage: chunked_asr.py SRC DENOISED_WAV CHUNK_SECONDS [OUTDIR]

  SRC           original media (duration reference)
  DENOISED_WAV  16 kHz mono WAV, already denoised (the audio actually sent)
  CHUNK_SECONDS e.g. 45 or 75
  OUTDIR        default /tmp/meralion_asr  (chunks + JSON results land here)

Always run this *in addition to* a whole-file pass. Which pass you treat as primary
depends on the audio — see SKILL.md ("Long files" and its counter-case).

Three guards learned the hard way (2026-09-22):
  1. The denoised WAV's duration is verified against SRC before chunking. A killed
     ffmpeg can leave a short-but-playable file, and the API gives NO signal that the
     tail is missing.
  2. A zero-length result is reported as a FAILURE, not as silence. The API returns
     HTTP 200 + empty content for empty/near-empty audio.
  3. Chunks shorter than 1.5 s are skipped rather than uploaded.
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

KEY = os.environ["MERALION_KEY"]
ENDPOINT = "https://api.meralion.ai/v1/audio/transcriptions"
MODEL = "MERaLiON/MERaLiON-3-3B-ASR-CTM"  # 10B silently falls back and returns empty
MIN_CHUNK = 1.5  # seconds; below this, don't bother uploading


def duration(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path]).decode().strip()
    return float(out)


def transcribe(path):
    b64 = base64.b64encode(open(path, "rb").read()).decode()
    body = {
        "audio_url": "data:audio/wav;base64," + b64,
        "model": MODEL,
        # both are accepted but do NOT surface in the response — don't promise them
        "return_diarization": False,
        "return_timestamps": False,
        "boundary_mode": "sequential",
    }
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(), method="POST")
    req.add_header("Authorization", "Bearer " + KEY)
    req.add_header("Content-Type", "application/json")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                j = json.loads(r.read().decode())
            msg = j.get("choices", [{}])[0].get("message", {})
            return msg.get("content") or j.get("text") or j.get("transcript") or ""
        except urllib.error.HTTPError as e:
            print("  HTTP %s %s" % (e.code, e.read().decode()[:200]), flush=True)
            time.sleep(25)
        except Exception as e:
            print("  ERR %r" % (e,), flush=True)
            time.sleep(25)
    return None  # all attempts failed


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    src, denoised, chunk = sys.argv[1], sys.argv[2], int(sys.argv[3])
    outdir = sys.argv[4] if len(sys.argv) > 4 else "/tmp/meralion_asr"
    os.makedirs(outdir, exist_ok=True)
    tag = os.path.splitext(os.path.basename(denoised))[0]

    # --- guard 1: the denoised file must actually cover the source -------------
    d_src, d_dn = duration(src), duration(denoised)
    if abs(d_src - d_dn) > 1.0:
        print("!! ABORT: denoised WAV is %.1fs but source is %.1fs (%.1fs missing)."
              % (d_dn, d_src, d_src - d_dn), flush=True)
        print("!! Re-run ffmpeg — the chunked pass would silently under-cover the tail.",
              flush=True)
        return 1
    print("duration ok: %.1fs (src %.1fs) -> chunks of %ds" % (d_dn, d_src, chunk), flush=True)

    results, empty = [], []
    start = 0.0
    i = 0
    while start < d_dn - MIN_CHUNK:
        length = min(chunk, d_dn - start)
        path = os.path.join(outdir, "%s_part%02d.wav" % (tag, i))
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-t", str(length),
             "-i", denoised, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", path],
            check=True)
        txt = transcribe(path)
        # --- guard 2: empty content is a failure signal, not silence -----------
        if txt is None:
            print("[%6.1fs] FAILED (no response after retries)" % start, flush=True)
        elif not txt.strip():
            empty.append(start)
            print("[%6.1fs] !! EMPTY — verify this segment is genuinely silent "
                  "(byte size: %d)" % (start, os.path.getsize(path)), flush=True)
        else:
            print("[%6.1fs] %s" % (start, txt), flush=True)
        results.append({"start": start, "seconds": length, "text": txt})
        start += chunk
        i += 1
        if start < d_dn - MIN_CHUNK:
            time.sleep(13)  # 5 rpm cap is the binding constraint

    with open(os.path.join(outdir, "%s_chunked.json" % tag), "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    total = sum(len(r["text"] or "") for r in results)
    print("DONE  chunks=%d  chars=%d  empty=%d %s"
          % (len(results), total, len(empty), empty or ""), flush=True)
    print("Now compare with the whole-file pass: if chunked is SHORTER than whole-file, "
          "investigate before publishing.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

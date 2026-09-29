#!/usr/bin/env python3
"""MERaLiON transcription smoke test that uses ONLY native arm64 system tools.

Purpose: verify the MERaLiON cloud ASR path on a machine where the WorkBuddy-managed
runtimes are x86_64 and Rosetta 2 is absent (so ffmpeg / managed python / managed node
all die with "Bad CPU type in executable"). Uses:

    /usr/bin/afconvert   m4a/mp3/... -> 16 kHz mono 16-bit WAV   (native)
    /usr/bin/afinfo      read duration / channel / rate          (native)
    /usr/bin/python3     3.8.2 universal: HTTPS POST + JSON      (native)
    /usr/bin/security    Keychain read of the meralion.ai key    (native)

Run with:  /usr/bin/python3 scripts/test_meralion.py /path/to/audio.m4a [chunk_seconds]

Outputs land in OUTDIR (default /tmp/asr_test): the converted WAV, the raw transcripts,
and a summary line per pass. Compare the character count against a known baseline, and
read the tail, before trusting a whole-file pass.
"""
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave

ENDPOINT = "https://api.meralion.ai/v1/audio/transcriptions"
# 10B silently falls back to 3-3B-ASR-CTM; request the 3B directly.
MODEL = "MERaLiON/MERaLiON-3-3B-ASR-CTM"
MIME = "audio/wav"
OUTDIR = "/tmp/asr_test"
AFCONVERT = "/usr/bin/afconvert"
AFINFO = "/usr/bin/afinfo"
SECURITY = "/usr/bin/security"
PY = "/usr/bin/python3"


def get_key():
    """Keychain, service-label only. Never hardcode or persist the key."""
    return subprocess.check_output(
        [SECURITY, "find-generic-password", "-s", "meralion.ai", "-w"]
    ).decode().strip()


def to_wav_16k_mono(src, dst):
    """m4a/mp3/wav -> 16 kHz mono 16-bit WAV using native afconvert."""
    subprocess.check_call([AFCONVERT, "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", src, dst])


def duration_seconds(path):
    """Native duration read. Do NOT skip this: a killed/partial convert still looks playable."""
    out = subprocess.check_output([AFINFO, path]).decode()
    m = re.search(r"estimated duration:\s*([\d.]+)", out)
    return float(m.group(1)) if m else None


def slice_wav(src, dst, start_s, dur_s):
    """PCM slice with the stdlib only - no ffmpeg. Returns (frames, actual_seconds)."""
    with wave.open(src, "rb") as w:
        nch, sw, fr = w.getnchannels(), w.getsampwidth(), w.getframerate()
        w.setpos(int(start_s * fr))
        frames = w.readframes(int(dur_s * fr))
    with wave.open(dst, "wb") as o:
        o.setnchannels(nch)
        o.setsampwidth(sw)
        o.setframerate(fr)
        o.writeframes(frames)
    return len(frames) // (nch * sw), len(frames) / (nch * sw) / fr


def post(path, key, label):
    """POST one file. Returns text, or None on any failure. Checks BOTH status and error key."""
    raw = open(path, "rb").read()
    b64 = base64.b64encode(raw).decode()
    body = {
        "audio_url": "data:%s;base64,%s" % (MIME, b64),
        "model": MODEL,
        "return_diarization": True,   # accepted but never surfaces - see SKILL.md
        "return_timestamps": True,    # accepted but never surfaces - see SKILL.md
        "boundary_mode": "sequential",
    }
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(body).encode(), method="POST"
    )
    req.add_header("Authorization", "Bearer " + key)
    req.add_header("Content-Type", "application/json")
    print("  [%s] body=%.2f MB base64 (%.2f MB raw)" % (label, len(b64) / 1e6, len(raw) / 1e6))
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            status, txt = r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        print("  [%s] HTTP %s after %.1fs :: %s"
              % (label, e.code, time.time() - t0, e.read().decode()[:400]))
        return None
    except Exception as e:
        print("  [%s] %s: %s after %.1fs" % (label, type(e).__name__, e, time.time() - t0))
        return None

    j = json.loads(txt)
    # A valid zero-sample WAV returns HTTP 200 with an error body. Status alone is not enough.
    if "error" in j:
        print("  [%s] HTTP %s but ERROR body: %s" % (label, status, json.dumps(j["error"])[:300]))
        return None
    try:
        content = j["choices"][0]["message"]["content"]
    except Exception:
        content = j.get("text") or j.get("transcript") or ""
    if not content.strip():
        print("  [%s] HTTP %s but EMPTY content" % (label, status))
        return None
    print("  [%s] HTTP %s  %.1fs  chars=%d  model=%s"
          % (label, status, time.time() - t0, len(content), j.get("model")))
    return content


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "/tmp/asr_test/input.m4a"
    chunk_s = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    os.makedirs(OUTDIR, exist_ok=True)
    wav = os.path.join(OUTDIR, "conv_16k.wav")

    key = get_key()
    print("key loaded: %d chars" % len(key))

    src_dur = duration_seconds(src)
    to_wav_16k_mono(src, wav)
    wav_dur = duration_seconds(wav)
    print("source %.1fs -> wav %.1fs" % (src_dur or -1, wav_dur or -1))
    if src_dur and wav_dur and abs(src_dur - wav_dur) > 1.0:
        sys.exit("ABORT: converted duration does not match source (partial convert?)")

    print("\n=== whole-file pass (primary on clean close-mic audio) ===")
    whole = post(wav, key, "whole")
    if whole:
        open(os.path.join(OUTDIR, "out_whole.txt"), "w").write(whole)
        print("  tail: %s" % whole[-200:].replace("\n", " "))

    if wav_dur and wav_dur > chunk_s:
        time.sleep(13)  # stay under the 5 rpm cap
        print("\n=== chunked cross-check (%ds) ===" % chunk_s)
        parts, n, t = [], 0, 0.0
        while t < wav_dur:
            d = min(chunk_s, wav_dur - t)
            p = os.path.join(OUTDIR, "part_%03d.wav" % n)
            slice_wav(wav, p, t, d)
            c = post(p, key, "part%03d@%.0fs" % (n, t))
            if c:
                parts.append(c)
            n += 1
            t += d
            time.sleep(13)
        joined = "\n".join(parts)
        open(os.path.join(OUTDIR, "out_chunked.txt"), "w").write(joined)
        print("\nwhole=%d chars  chunked=%d chars  delta=%.1f%%"
              % (len(whole or ""), len(joined),
                 100.0 * (len(joined) - len(whole or "")) / max(1, len(whole or ""))))
        print("SYMPTOM TO WATCH: chunked < whole means the chunked pass MISSED audio.")

    print("\nDONE - outputs in %s" % OUTDIR)


if __name__ == "__main__":
    main()

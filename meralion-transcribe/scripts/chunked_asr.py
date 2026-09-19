#!/usr/bin/env python3
"""Fine-grained chunked transcription on denoised WAV, to triangulate a noisy recording.

Usage: chunked_asr.py SRC DENOISED_WAV CHUNK_SECONDS [OUTDIR]
  SRC           original media (used only to read duration)
  DENOISED_WAV  16 kHz mono WAV, already denoised
  CHUNK_SECONDS e.g. 45 or 75
  OUTDIR        default /tmp/meralion_asr  (chunks + JSON results land here)

Always run this in addition to a whole-file pass — see the SKILL.md note on silent omission.
"""
import base64, json, os, subprocess, sys, time, urllib.request, urllib.error

KEY = os.environ["MERALION_KEY"]
ENDPOINT = "https://api.meralion.ai/v1/audio/transcriptions"
SRC, TAG, CHUNK = sys.argv[1], sys.argv[2], int(sys.argv[3])
outdir = sys.argv[4] if len(sys.argv) > 4 else "/tmp/meralion_asr"
os.makedirs(outdir, exist_ok=True)

dur = float(subprocess.check_output([
    "ffprobe", "-v", "error", "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1", SRC]).decode().strip())
n = int(dur // CHUNK) + 1
print("duration=%.1fs -> %d chunks of %ds" % (dur, n, CHUNK), flush=True)

results = []
for i in range(n):
    start = i * CHUNK
    path = "%s/part%02d.wav" % (outdir, i)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-t", str(CHUNK),
                    "-i", SRC, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", path], check=True)
    b64 = base64.b64encode(open(path, "rb").read()).decode()
    body = {"audio_url": "data:audio/wav;base64," + b64,
            "model": "MERaLiON/MERaLiON-3-3B-ASR-CTM",
            "return_diarization": False, "return_timestamps": False,
            "boundary_mode": "sequential"}
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(), method="POST")
    req.add_header("Authorization", "Bearer " + KEY)
    req.add_header("Content-Type", "application/json")
    txt = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                j = json.loads(r.read().decode())
            txt = j["choices"][0]["message"]["content"] or ""
            break
        except urllib.error.HTTPError as e:
            print("  HTTP %s %s" % (e.code, e.read().decode()[:200]), flush=True)
            time.sleep(25)
        except Exception as e:
            print("  ERR %r" % (e,), flush=True)
            time.sleep(25)
    mm, ss = divmod(start, 60)
    print("[%02d:%02d] %s" % (mm, ss, txt), flush=True)
    results.append({"start": start, "text": txt})
    if i < n - 1:
        time.sleep(13)

with open(os.path.join(outdir, "%s_chunked.json" % TAG), "w") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("DONE", flush=True)

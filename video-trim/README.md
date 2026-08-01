# video-trim

Trim one or more time segments out of a video and stitch the kept parts into a single output file — no quality loss, no upload, fully local.

## What It Does

- **Single trim** — cut a video down to one start/end range
- **Multi-segment stitch** — keep several ranges ("keep 12:21–47:56 and 55:00–1:02:00") and concatenate them in order into one output file
- **Remove-a-section edits** — describe what to cut out and the skill inverts it into keep-segments for you
- Built on `ffmpeg`/`ffprobe` — runs entirely on your machine, no API calls, no polling

## Setup

### Claude Code
```bash
git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/greggchen308/gc-skills.git
cd gc-skills
git sparse-checkout set video-trim
mv video-trim ~/.claude/skills/
```
Or download the folder directly and place it at `~/.claude/skills/video-trim`.

Then invoke with `/video-trim`, or just ask to trim/cut/stitch a video with timestamps.

### Requirements
- Python 3 (for the script)
- `ffmpeg` and `ffprobe` on `PATH`

## How It Works

1. **Inspect** — `ffprobe` reads the source's resolution, codec, and duration before touching anything, so requested timestamps can be validated against real duration
2. **Cut** — each kept segment is extracted to a scratch temp directory
3. **Stitch** — if there's more than one segment, they're concatenated in the order given
4. **Verify** — `ffprobe` runs again on the output to confirm resolution/codec are unchanged

Source files are never modified — output is always a new file, written next to the source as `<name>_trimmed.mp4` by default.

## Two Modes

| Mode | How | Cut accuracy | Quality | Speed |
|---|---|---|---|---|
| **lossless** (default) | stream copy, no re-encode | snaps to nearest keyframe (±1-2s) | bit-identical to source | near-instant |
| **reencode** | libx264 at source's own bitrate | frame-accurate | visually lossless, not bit-identical | proportional to video length |

Lossless is the default — fast and zero-loss, but a cut boundary can land up to ~1-2 seconds off the requested timestamp. Use reencode when a cut needs to be frame-exact (e.g. cutting mid-sentence in a talking-head video).

## Usage

Write a spec and run the script directly:
```json
{
  "source": "/absolute/path/to/source.mp4",
  "output": "/absolute/path/to/output.mp4",
  "segments": [
    {"start": "12:21", "end": "47:56"},
    {"start": "55:00", "end": "1:02:00"}
  ],
  "mode": "lossless"
}
```
```bash
python3 scripts/trim_and_stitch.py spec.json
```
Timestamps accept `HH:MM:SS`, `MM:SS`, or raw seconds. Prints one JSON result line:
- `{"status": "ok", "output": "...", "segments_used": [...], "mode": "..."}`
- `{"status": "error", "message": "..."}` on bad timestamps, out-of-range segments, or an ffmpeg failure

## See Also

- `SKILL.md` — full trigger conditions, mode-selection guidance, and reporting format
- `scripts/trim_and_stitch.py` — the trim/stitch implementation

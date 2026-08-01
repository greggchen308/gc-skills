---
name: video-trim
description: Trim one or more time segments out of a video and stitch the kept parts into a single output file, without compromising resolution or quality. Handles single-segment trims and multi-segment "keep these parts, cut everything else, stitch together" edits. Triggers on "/video-trim", "trim this video", "cut this video from X to Y", "keep only this part of the video", "stitch these clips together", or a request giving one or more start/end timestamps for a video file.
---

# video-trim

## Summary
Cuts a source video down to one or more kept segments (each given as a start/end timestamp) and, when there's more than one segment, stitches the kept parts into a single output file in the order given. Built around `ffmpeg`/`ffprobe` (already installed at `/usr/local/bin/ffmpeg`). Runs locally — no upload, no API, no polling.

## Step 0: Confirm the ask
If Gregg gave a file path and one start/end pair already, no need to ask anything — proceed straight to step 1. Only use AskUserQuestion if segments, order, or output location are actually ambiguous (e.g. he says "cut out the boring middle part" without timestamps — ask for the timestamps, don't guess them).

Multiple segments are additive keeps, not exclusions: "keep 12:21–47:56 and 55:00–1:02:00" means the output contains those two ranges back-to-back, in the order listed, with everything else dropped. If Gregg instead describes segments to *remove* ("cut out 20:00–22:00"), invert it yourself into keep-segments (everything before, everything after) before building the spec — confirm the inverted ranges with him if the video has more than 2 segments as a result, since silent misordering here is hard to notice after the fact.

## Step 1: Inspect the source
Always run this first, even if Gregg states the duration — ground truth over assumption:
```bash
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,r_frame_rate,bit_rate -show_entries format=duration,size -of default=noprint_wrappers=1 "<source_path>"
```
Confirms the file exists, and gives you resolution/codec/duration/bitrate to validate requested timestamps against (reject or flag any segment start/end beyond the source duration) and to report back after the edit ("still 1920x1080, same codec").

## Step 2: Pick a mode
Two modes, pick based on what matters more for this job:

| Mode | How | Cut accuracy | Quality | Speed |
|---|---|---|---|---|
| **lossless** (default) | stream copy, no re-encode | snaps to nearest keyframe — boundary can land up to ~1-2s off the requested timestamp | zero loss (bit-identical to source) | very fast (seconds, near-instant regardless of video length) |
| **reencode** | libx264 re-encode at source's own bitrate (or CRF 18 if bitrate unknown) | frame-accurate | visually lossless but not bit-identical (re-encoded) | slower, roughly proportional to total video length |

Default to **lossless** unless Gregg needs exact frame-accurate cuts (e.g. cutting mid-sentence in a talking-head video where a keyframe-snap would leave 1-2s of unwanted content). If he hasn't said and the use case sounds precision-sensitive, ask once via AskUserQuestion; otherwise just use lossless and mention the keyframe-snap caveat when reporting results so he can ask for a redo in reencode mode if a cut looks off.

## Step 3: Build the spec and run
Write a spec JSON to scratch:
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
- Timestamps accept `HH:MM:SS`, `MM:SS`, or raw seconds — mirror whatever format Gregg gave.
- Default `output` path: same directory as source, filename `<original_stem>_trimmed.mp4` (or `_trimmed_2.mp4` etc. if that already exists — never silently overwrite an existing file without checking first).

Run:
```bash
python3 /Users/GreggChen/.claude/skills/video-trim/scripts/trim_and_stitch.py <spec.json>
```
This validates every segment against the source duration, cuts each one to a scratch temp dir, concatenates them in order (skipped if only one segment), cleans up the temp dir, and prints one JSON line:
- `{"status": "ok", "output": "...", "segments_used": [...], "mode": "..."}`
- `{"status": "error", "message": "..."}` (bad timestamp, segment beyond duration, ffmpeg failure) — report the message verbatim, don't guess a fix.

## Step 4: Verify and report
Run the Step 1 ffprobe command again on the **output** file. Confirm resolution/codec match the source (they should, in both modes — reencode matches source bitrate rather than dropping it), then report to Gregg:
- Output file path
- Resulting duration (should equal sum of segment lengths, ± the keyframe-snap tolerance in lossless mode)
- Resolution/codec confirmation ("still 1920x1080, same codec — no quality loss")
- If lossless mode was used: one line noting cuts may be off by up to ~1-2s at each boundary, and that reencode mode is available if a cut looks visibly wrong

Keep the report short — this is a local file operation, not a deliverable needing a written summary doc.

## Notes
- This is a fully local, deterministic ffmpeg wrapper — no subagent needed for a single request. Only worth backgrounding if reencode mode is used on a very long video and Gregg has other work to hand you in the meantime.
- Source files are never modified — output is always a new file.
- If Gregg gives overlapping or out-of-order segments, use the order he specified (that's a valid creative choice, e.g. reordering clips), but flag if segments overlap each other since that's more often a mistake than intentional.

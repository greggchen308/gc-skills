#!/usr/bin/env python3
"""Trim one or more segments from a source video and stitch them into one output.

Usage:
    python3 trim_and_stitch.py <spec.json>

spec.json shape:
{
  "source": "/absolute/path/to/source.mp4",
  "output": "/absolute/path/to/output.mp4",
  "segments": [
    {"start": "12:21", "end": "47:56"},
    {"start": "1:02:00", "end": "1:05:30"}
  ],
  "mode": "lossless" | "reencode"
}

Timestamps accept HH:MM:SS, MM:SS, or raw seconds (int/float), as strings.

Modes:
  lossless  - stream copy (-c copy). Fastest, zero quality loss, but each cut
              snaps to the nearest preceding keyframe, so actual segment
              boundaries can land up to ~1-2s off the requested timestamp
              (only relevant with multiple segments being concatenated;
              a single segment just runs slightly long/short at the edges).
  reencode  - frame-accurate cuts, re-encoded with libx264 at a bitrate
              matched to the source (so resolution/quality is preserved,
              not "compressed"). Slower, proportional to video length.

Prints a JSON result line on success:
  {"status": "ok", "output": "...", "segments_used": [...], "mode": "..."}
On failure, prints {"status": "error", "message": "..."} and exits 1.
"""
import json
import subprocess
import sys
import os
import tempfile
import shutil


def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def parse_timestamp(ts):
    """Accepts 'HH:MM:SS', 'MM:SS', or a raw number of seconds. Returns float seconds."""
    if isinstance(ts, (int, float)):
        return float(ts)
    ts = str(ts).strip()
    if ":" not in ts:
        return float(ts)
    parts = ts.split(":")
    parts = [float(p) for p in parts]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, s = parts[-3], parts[-2], parts[-1]
    return h * 3600 + m * 60 + s


def fmt_ts(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def ffprobe_duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path])
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe failed on source: {r.stderr.strip()}")
    return float(r.stdout.strip())


def ffprobe_video_info(path):
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,r_frame_rate,bit_rate",
             "-of", "default=noprint_wrappers=1", path])
    info = {}
    for line in r.stdout.strip().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info[k] = v
    return info


def main():
    if len(sys.argv) != 2:
        print(json.dumps({"status": "error", "message": "usage: trim_and_stitch.py <spec.json>"}))
        sys.exit(1)

    spec_path = sys.argv[1]
    with open(spec_path) as f:
        spec = json.load(f)

    source = spec["source"]
    output = spec["output"]
    segments = spec["segments"]
    mode = spec.get("mode", "lossless")

    if not os.path.isfile(source):
        print(json.dumps({"status": "error", "message": f"source file not found: {source}"}))
        sys.exit(1)

    if mode not in ("lossless", "reencode"):
        print(json.dumps({"status": "error", "message": f"invalid mode: {mode}"}))
        sys.exit(1)

    if not segments:
        print(json.dumps({"status": "error", "message": "no segments provided"}))
        sys.exit(1)

    try:
        duration = ffprobe_duration(source)
    except RuntimeError as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        sys.exit(1)

    # Parse + validate segments
    parsed = []
    for i, seg in enumerate(segments):
        try:
            start = parse_timestamp(seg["start"])
            end = parse_timestamp(seg["end"])
        except (KeyError, ValueError) as e:
            print(json.dumps({"status": "error", "message": f"segment {i}: bad timestamp ({e})"}))
            sys.exit(1)
        if start < 0 or end < 0:
            print(json.dumps({"status": "error", "message": f"segment {i}: negative timestamp"}))
            sys.exit(1)
        if end <= start:
            print(json.dumps({"status": "error", "message": f"segment {i}: end ({fmt_ts(end)}) must be after start ({fmt_ts(start)})"}))
            sys.exit(1)
        if start > duration:
            print(json.dumps({"status": "error", "message": f"segment {i}: start ({fmt_ts(start)}) is beyond source duration ({fmt_ts(duration)})"}))
            sys.exit(1)
        if end > duration:
            end = duration  # clamp instead of failing
        parsed.append((start, end))

    video_info = ffprobe_video_info(source)
    src_bitrate = video_info.get("bit_rate")

    workdir = tempfile.mkdtemp(prefix="video_trim_")
    segment_files = []

    try:
        for i, (start, end) in enumerate(parsed):
            seg_out = os.path.join(workdir, f"segment_{i:03d}.mp4")
            if mode == "lossless":
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", fmt_ts(start), "-to", fmt_ts(end),
                    "-i", source,
                    "-c", "copy", "-avoid_negative_ts", "make_zero",
                    seg_out,
                ]
            else:
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", fmt_ts(start), "-to", fmt_ts(end),
                    "-i", source,
                    "-c:v", "libx264", "-preset", "medium",
                ]
                if src_bitrate:
                    cmd += ["-b:v", src_bitrate]
                else:
                    cmd += ["-crf", "18"]
                cmd += ["-c:a", "aac", "-b:a", "192k", seg_out]

            r = run(cmd)
            if r.returncode != 0 or not os.path.isfile(seg_out):
                print(json.dumps({
                    "status": "error",
                    "message": f"ffmpeg failed on segment {i} ({fmt_ts(start)}-{fmt_ts(end)}): {r.stderr[-800:]}"
                }))
                sys.exit(1)
            segment_files.append(seg_out)

        if len(segment_files) == 1:
            shutil.move(segment_files[0], output)
        else:
            concat_list = os.path.join(workdir, "concat_list.txt")
            with open(concat_list, "w") as f:
                for sf in segment_files:
                    f.write(f"file '{sf}'\n")
            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_list, "-c", "copy", output,
            ]
            r = run(cmd)
            if r.returncode != 0 or not os.path.isfile(output):
                print(json.dumps({
                    "status": "error",
                    "message": f"concat failed: {r.stderr[-800:]}"
                }))
                sys.exit(1)

        print(json.dumps({
            "status": "ok",
            "output": output,
            "segments_used": [{"start": fmt_ts(s), "end": fmt_ts(e)} for s, e in parsed],
            "mode": mode,
        }))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Generic DashScope-style async video-generation submitter.
Reads a JSON request spec from a file, POSTs it to the provider's
video-synthesis endpoint with X-DashScope-Async: enable, and prints the
task_id + initial status. Does NOT poll — polling is a separate step
(check_video.py) driven by the agent's own scheduling.

Usage:
  python3 submit_video.py <spec.json>

spec.json shape:
{
  "api_url": "https://.../video-generation/video-synthesis",
  "api_key_env": "DASHSCOPE_API_KEY",
  "model": "wan3.0-video",
  "input": { ... mode-specific shape, built by the skill flow ... },
  "parameters": { "resolution": "480P", "ratio": "adaptive", "duration": -1,
                   "audio": true, "prompt_extend": true, "watermark": false, ... }
}

"input" examples (Wan 3.0, unified media[] with a "type" field):
  text-to-video    {"prompt": "..."}
  first frame      {"prompt": "...", "media": [{"type": "first_frame", "url": "..."}]}
  omni-reference   {"prompt": "...Image 1...Video 1...", "media": [
                     {"type": "reference_image", "url": "..."},
                     {"type": "reference_video", "url": "oss://..."},
                     {"type": "reference_audio", "url": "oss://..."}]}
  deck -> video    {"prompt": "...", "media": [{"type": "file", "url": "oss://.../deck.pptx"}]}
  web page -> video {"prompt": "...", "media": [{"type": "link", "url": "https://..."}]}
(Legacy wan2.7-* uses different media types — see SKILL.md appendix.)

The "input" object is passed through as-is — the skill (not this script) is
responsible for shaping it per mode, including converting local image paths to
data: URIs and uploading local video/audio/file assets to oss:// URLs
(scripts/upload_asset.py) beforehand. If any media URL is an oss:// temp URL,
this script automatically adds the "X-DashScope-OssResourceResolve: enable"
header so the provider can resolve it. This script's only job is the HTTP call
and response parsing, since the input shape varies too much per mode to
hardcode here.
"""
import json
import os
import sys
import urllib.request
import urllib.error


def main():
    if len(sys.argv) != 2:
        print("Usage: submit_video.py <spec.json>", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1]) as f:
        spec = json.load(f)

    api_key = os.environ.get(spec["api_key_env"], "")
    if not api_key:
        print(f"ERROR: env var {spec['api_key_env']} is not set or empty.", file=sys.stderr)
        sys.exit(2)

    body = {
        "model": spec["model"],
        "input": spec["input"],
        "parameters": spec.get("parameters", {}),
    }
    body_bytes = json.dumps(body).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-DashScope-Async": "enable",
    }
    # oss:// temp URLs (from upload_asset.py) only resolve when this header is set.
    if "oss://" in json.dumps(spec["input"]):
        headers["X-DashScope-OssResourceResolve"] = "enable"

    req = urllib.request.Request(
        spec["api_url"],
        data=body_bytes,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} error from provider:", file=sys.stderr)
        print(e.read().decode("utf-8", errors="replace"), file=sys.stderr)
        sys.exit(3)

    result = json.loads(raw)
    output = result.get("output", {})
    task_id = output.get("task_id")
    task_status = output.get("task_status")

    if not task_id:
        print("ERROR: no task_id in response:", json.dumps(result), file=sys.stderr)
        sys.exit(4)

    print(json.dumps({
        "task_id": task_id,
        "task_status": task_status,
        "request_id": result.get("request_id", ""),
    }))


if __name__ == "__main__":
    main()

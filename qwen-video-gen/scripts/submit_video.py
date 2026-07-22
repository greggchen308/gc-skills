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
  "model": "wan2.7-t2v-2026-06-12",
  "input": { ... mode-specific shape, built by the skill flow ... },
  "parameters": { "resolution": "720P", "ratio": "16:9", "duration": 10,
                   "prompt_extend": true, "watermark": false, ... }
}

The "input" object is passed through as-is — the skill (not this script)
is responsible for shaping it correctly per mode (t2v / i2v / r2v / videoedit /
extend / audio-driven), including converting any local file paths in media
URLs to data URIs beforehand if needed. This script's only job is the HTTP
call and response parsing, since the input shape varies too much per mode
to hardcode here.
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

    req = urllib.request.Request(
        spec["api_url"],
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "X-DashScope-Async": "enable",
        },
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

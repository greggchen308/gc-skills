#!/usr/bin/env python3
"""
Checks a DashScope async task status by task_id.
Caller (the skill flow) inspects task_status:
  PENDING / RUNNING  -> not done, schedule another check
  SUCCEEDED          -> video is downloaded locally, local_path is ready
  FAILED             -> output.code / output.message explain why

Usage:
  python3 check_video.py <task_id> <api_key_env> <base_url> <output_path>

base_url MUST be the same host used for submission (e.g. the WorkspaceId-scoped
"https://{host}.cn-beijing.maas.aliyuncs.com" from providers.json) — task-status
lives on that same host at /api/v1/tasks/{task_id}, not a separate global host.

output_path is where the video gets saved once SUCCEEDED. Required even for
PENDING/RUNNING checks (so the caller doesn't need a different invocation per
poll) but only used once the task actually succeeds.

IMPORTANT — never print the raw signed video_url to stdout/chat as a bare
string. Some agent runtimes (e.g. OpenClaw, see openclaw/openclaw#112839)
hard-truncate long tool-output strings at a fixed character count, which cuts
signed OSS URLs mid-query-string (right through OSSAccessKeyId/Signature) and
produces an unusable, un-recoverable link. This script always downloads the
video to output_path and reports only the local path + a short status line —
short strings survive any display-layer truncation intact.
"""
import json
import os
import sys
import urllib.request
import urllib.error


def main():
    if len(sys.argv) != 5:
        print("Usage: check_video.py <task_id> <api_key_env> <tasks_base_url> <output_path>", file=sys.stderr)
        sys.exit(1)

    task_id = sys.argv[1]
    api_key_env = sys.argv[2]
    base_url = sys.argv[3]
    output_path = os.path.expanduser(sys.argv[4])

    api_key = os.environ.get(api_key_env, "")
    if not api_key:
        print(f"ERROR: env var {api_key_env} is not set or empty.", file=sys.stderr)
        sys.exit(2)

    url = f"{base_url.rstrip('/')}/api/v1/tasks/{task_id}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
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
    task_status = output.get("task_status")

    if task_status != "SUCCEEDED":
        print(json.dumps({
            "task_status": task_status,
            "code": output.get("code"),
            "message": output.get("message"),
        }))
        return

    video_url = output.get("video_url")
    if not video_url:
        print(json.dumps({"task_status": "FAILED", "message": "SUCCEEDED but no video_url in response"}))
        sys.exit(4)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with urllib.request.urlopen(video_url, timeout=120) as video_resp:
        with open(output_path, "wb") as f:
            f.write(video_resp.read())

    print(json.dumps({
        "task_status": "SUCCEEDED",
        "local_path": output_path,
    }))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Checks a DashScope async task status by task_id. Prints the raw task JSON.
Caller (the skill flow) inspects task_status:
  PENDING / RUNNING  -> not done, schedule another check
  SUCCEEDED          -> output.video_url is ready (signed, time-limited)
  FAILED             -> output.code / output.message explain why

Usage:
  python3 check_video.py <task_id> <api_key_env> <base_url>

base_url MUST be the same host used for submission (e.g. the WorkspaceId-scoped
"https://{host}.cn-beijing.maas.aliyuncs.com" from providers.json) — task-status
lives on that same host at /api/v1/tasks/{task_id}, not a separate global host.
"""
import json
import os
import sys
import urllib.request
import urllib.error


def main():
    if len(sys.argv) != 4:
        print("Usage: check_video.py <task_id> <api_key_env> <tasks_base_url>", file=sys.stderr)
        sys.exit(1)

    task_id = sys.argv[1]
    api_key_env = sys.argv[2]
    base_url = sys.argv[3]

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

    print(raw.decode("utf-8"))


if __name__ == "__main__":
    main()

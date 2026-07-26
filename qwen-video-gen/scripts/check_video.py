#!/usr/bin/env python3
"""
Checks a DashScope async task status by task_id.
Caller (the skill flow) inspects task_status:
  PENDING / RUNNING  -> not done, schedule another check
  SUCCEEDED          -> result delivered per --mode (see below)
  FAILED             -> code / message explain why

Usage:
  python3 check_video.py <task_id> <api_key_env> <base_url> --mode=download --output-path=<path>
  python3 check_video.py <task_id> <api_key_env> <base_url> --mode=link --url-file=<path>

base_url MUST be the same host used for submission (e.g. the WorkspaceId-scoped
"https://{host}.cn-beijing.maas.aliyuncs.com" from providers.json) — task-status
lives on that same host at /api/v1/tasks/{task_id}, not a separate global host.

Two delivery modes, chosen by the skill flow after asking Gregg (see SKILL.md
step 8):
  --mode=download  Downloads the video to --output-path and reports only that
                    local path. Use when Gregg wants a local file.
  --mode=link       Writes the full signed video_url to --url-file (never to
                    stdout) and reports only the file path. Use when Gregg
                    wants a shareable hosted link instead of a local copy.

Neither mode ever prints the raw signed video_url to stdout/chat as a bare
string. Some agent runtimes (e.g. OpenClaw, see openclaw/openclaw#112839)
hard-truncate long tool-output strings at a fixed character count, which cuts
signed OSS URLs mid-query-string (right through OSSAccessKeyId/Signature) and
produces an unusable, un-recoverable link. Writing the URL to a file and
reporting only the file path sidesteps this regardless of which mode Gregg
picked — short strings survive any display-layer truncation intact.
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("task_id")
    parser.add_argument("api_key_env")
    parser.add_argument("base_url")
    parser.add_argument("--mode", choices=["download", "link"], required=True)
    parser.add_argument("--output-path", help="required if --mode=download")
    parser.add_argument("--url-file", help="required if --mode=link")
    args = parser.parse_args()

    if args.mode == "download" and not args.output_path:
        print("ERROR: --output-path is required for --mode=download", file=sys.stderr)
        sys.exit(1)
    if args.mode == "link" and not args.url_file:
        print("ERROR: --url-file is required for --mode=link", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get(args.api_key_env, "")
    if not api_key:
        print(f"ERROR: env var {args.api_key_env} is not set or empty.", file=sys.stderr)
        sys.exit(2)

    url = f"{args.base_url.rstrip('/')}/api/v1/tasks/{args.task_id}"
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

    if args.mode == "download":
        output_path = os.path.expanduser(args.output_path)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with urllib.request.urlopen(video_url, timeout=120) as video_resp:
            with open(output_path, "wb") as f:
                f.write(video_resp.read())
        print(json.dumps({"task_status": "SUCCEEDED", "mode": "download", "local_path": output_path}))
    else:
        url_file = os.path.expanduser(args.url_file)
        os.makedirs(os.path.dirname(url_file) or ".", exist_ok=True)
        with open(url_file, "w") as f:
            f.write(video_url)
        print(json.dumps({"task_status": "SUCCEEDED", "mode": "link", "url_file": url_file}))


if __name__ == "__main__":
    main()

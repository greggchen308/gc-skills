#!/usr/bin/env python3
"""
Upload a local file to DashScope / Model Studio temporary storage and print the
resulting oss:// URL (valid ~48h), for use as a media[].url in a Wan 3.0
video-synthesis request (reference_video / reference_audio / file, or a large
reference_image).

Why this exists: Wan 3.0's `file` (deck/PDF/doc), `reference_video`, and
`reference_audio` inputs need a public https:// URL or an oss:// temp URL — only
images accept inline base64 data: URIs. This script does the two-step
"get upload credential -> POST to OSS" dance so the skill can point at a local
path (a .pptx deck, an .mp4 clip, an .mp3 voice sample) directly.

Usage:
  python3 upload_asset.py <local_file_path> <api_key_env> <model_name> [--api-base=https://dashscope.aliyuncs.com]

  <model_name> MUST be the same model that will consume the file (DashScope
  "model consistency" rule) — e.g. wan3.0-video or wan3.0-video-prime.
  --api-base defaults to the GLOBAL host (providers.json -> upload_api_base),
  NOT the workspace-scoped MaaS host used for generation.

On success prints one JSON line:
  {"oss_url": "oss://dashscope-instant/.../file.ext", "expires_in_hours": 48, "bytes": <n>}

After this, submit_video.py automatically adds the
"X-DashScope-OssResourceResolve: enable" header when it sees the oss:// URL in
the request input.

Exit codes: 1 usage error, 2 missing/empty api key env var, 3 HTTP error from
DashScope or OSS (body dumped to stderr), 4 unexpected response shape / file too
large.
"""
import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid


def _die(msg, code):
    print(msg, file=sys.stderr)
    sys.exit(code)


def _get_field(data, *names):
    for n in names:
        if n in data and data[n] not in (None, ""):
            return data[n]
    return None


def get_policy(api_base, api_key, model_name):
    qs = urllib.parse.urlencode({"action": "getPolicy", "model": model_name})
    url = f"{api_base.rstrip('/')}/api/v1/uploads?{qs}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} getting upload policy:", file=sys.stderr)
        print(e.read().decode("utf-8", errors="replace"), file=sys.stderr)
        sys.exit(3)
    body = json.loads(raw)
    data = body.get("data") or {}
    if not data:
        _die(f"ERROR: no 'data' in getPolicy response: {json.dumps(body)}", 4)
    return data


def build_multipart(fields, file_field, filename, file_bytes):
    """fields: list of (name, value) text parts, in order. file part goes last."""
    boundary = "----qwenvideo" + uuid.uuid4().hex
    crlf = b"\r\n"
    out = []
    for name, value in fields:
        out.append(b"--" + boundary.encode())
        out.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        out.append(b"")
        out.append(str(value).encode())
    ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    out.append(b"--" + boundary.encode())
    out.append(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"'.encode()
    )
    out.append(f"Content-Type: {ctype}".encode())
    out.append(b"")
    body = crlf.join(out) + crlf + file_bytes + crlf
    body += b"--" + boundary.encode() + b"--" + crlf
    return body, boundary


def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("file_path")
    parser.add_argument("api_key_env")
    parser.add_argument("model_name")
    parser.add_argument("--api-base", default="https://dashscope.aliyuncs.com")
    if len(sys.argv) == 1:
        parser.print_usage(sys.stderr)
        sys.exit(1)
    args = parser.parse_args()

    path = os.path.expanduser(args.file_path)
    if not os.path.isfile(path):
        _die(f"ERROR: not a file: {path}", 1)

    api_key = os.environ.get(args.api_key_env, "")
    if not api_key:
        _die(f"ERROR: env var {args.api_key_env} is not set or empty.", 2)

    size = os.path.getsize(path)
    filename = os.path.basename(path)

    data = get_policy(args.api_base, api_key, args.model_name)

    max_mb = _get_field(data, "max_file_size_mb")
    if max_mb:
        try:
            if size > float(max_mb) * 1024 * 1024:
                _die(f"ERROR: {filename} is {size} bytes, over the {max_mb} MB limit for {args.model_name}.", 4)
        except ValueError:
            pass

    upload_host = _get_field(data, "upload_host")
    upload_dir = _get_field(data, "upload_dir")
    policy = _get_field(data, "policy")
    signature = _get_field(data, "signature")
    access_key_id = _get_field(data, "oss_access_key_id", "OSSAccessKeyId", "access_key_id")
    object_acl = _get_field(data, "x_oss_object_acl", "x-oss-object-acl")
    forbid_overwrite = _get_field(data, "x_oss_forbid_overwrite", "x-oss-forbid-overwrite")

    missing = [n for n, v in [
        ("upload_host", upload_host), ("upload_dir", upload_dir),
        ("policy", policy), ("signature", signature),
        ("oss_access_key_id", access_key_id),
    ] if not v]
    if missing:
        _die(f"ERROR: getPolicy response missing {missing}: {json.dumps(data)}", 4)

    key = f"{upload_dir}/{filename}"

    # Field order matters; the file part must be last.
    fields = [("OSSAccessKeyId", access_key_id), ("policy", policy), ("Signature", signature),
              ("key", key)]
    if object_acl is not None:
        fields.append(("x-oss-object-acl", object_acl))
    if forbid_overwrite is not None:
        fields.append(("x-oss-forbid-overwrite", forbid_overwrite))
    fields.append(("success_action_status", "200"))

    with open(path, "rb") as f:
        file_bytes = f.read()

    body, boundary = build_multipart(fields, "file", filename, file_bytes)
    req = urllib.request.Request(
        upload_host,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            _ = resp.read()
            status = resp.getcode()
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} uploading to OSS:", file=sys.stderr)
        print(e.read().decode("utf-8", errors="replace"), file=sys.stderr)
        sys.exit(3)

    if status not in (200, 201, 204):
        _die(f"ERROR: unexpected OSS upload status {status}", 4)

    print(json.dumps({
        "oss_url": f"oss://{key}",
        "expires_in_hours": 48,
        "bytes": size,
    }))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Generic multimodal image-generation caller.
Reads a JSON request spec from a file (or stdin) and POSTs it to the given
API URL, using an API key from an environment variable. Handles:
  - text-to-image generation
  - image edit (one input image + text instruction)
  - multi-image combine (multiple input images + text instruction)
Local image paths in the spec are base64-encoded into data URIs before sending.
The resulting image(s) are downloaded to the requested output path(s).

Usage:
  python3 call_provider.py <spec.json>

spec.json shape:
{
  "api_url": "https://.../generation",
  "api_key_env": "DASHSCOPE_API_KEY",
  "model": "qwen-image-2.0-pro-2026-04-22",
  "prompt": "text prompt",
  "input_images": ["/local/path.png", "https://already-hosted/img.jpg"],
  "negative_prompt": "...",
  "prompt_extend": true,
  "watermark": false,
  "size": "2048*2048",
  "n": 1,
  "output_paths": ["/abs/path/to/save1.png"]
}
"""
import base64
import json
import mimetypes
import os
import sys
import urllib.request


def to_data_uri_or_url(image_ref: str) -> str:
    if image_ref.startswith("http://") or image_ref.startswith("https://"):
        return image_ref
    path = os.path.expanduser(image_ref)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Input image not found: {image_ref}")
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def build_content(spec: dict) -> list:
    content = []
    for img in spec.get("input_images", []) or []:
        content.append({"image": to_data_uri_or_url(img)})
    content.append({"text": spec["prompt"]})
    return content


def main():
    if len(sys.argv) != 2:
        print("Usage: call_provider.py <spec.json>", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1]) as f:
        spec = json.load(f)

    api_key = os.environ.get(spec["api_key_env"], "")
    if not api_key:
        print(f"ERROR: env var {spec['api_key_env']} is not set or empty.", file=sys.stderr)
        sys.exit(2)

    body = {
        "model": spec["model"],
        "input": {
            "messages": [
                {"role": "user", "content": build_content(spec)}
            ]
        },
        "parameters": {
            "negative_prompt": spec.get("negative_prompt", " "),
            "prompt_extend": bool(spec.get("prompt_extend", True)),
            "watermark": bool(spec.get("watermark", False)),
            "size": spec.get("size", "2048*2048"),
        },
    }
    if spec.get("n"):
        body["parameters"]["n"] = spec["n"]

    req = urllib.request.Request(
        spec["api_url"],
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} error from provider:", file=sys.stderr)
        print(e.read().decode("utf-8", errors="replace"), file=sys.stderr)
        sys.exit(3)

    result = json.loads(raw)
    choices = result.get("output", {}).get("choices", [])
    if not choices:
        print("ERROR: no choices in response:", json.dumps(result), file=sys.stderr)
        sys.exit(4)

    image_urls = []
    for choice in choices:
        for item in choice.get("message", {}).get("content", []):
            if "image" in item:
                image_urls.append(item["image"])

    if not image_urls:
        print("ERROR: no image URLs in response:", json.dumps(result), file=sys.stderr)
        sys.exit(5)

    output_paths = spec.get("output_paths", [])
    saved = []
    for i, url in enumerate(image_urls):
        out_path = output_paths[i] if i < len(output_paths) else f"./generated_{i}.png"
        out_path = os.path.expanduser(out_path)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with urllib.request.urlopen(url, timeout=120) as img_resp:
            data = img_resp.read()
        with open(out_path, "wb") as f:
            f.write(data)
        saved.append(out_path)

    print(json.dumps({"saved": saved, "request_id": result.get("request_id", "")}))


if __name__ == "__main__":
    main()

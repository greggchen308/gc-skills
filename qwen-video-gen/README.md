# qwen-video-gen

Async video synthesis via DashScope/Qwen video-generation APIs.

## What It Does

Primary path is the **Wan 3.0** family (`wan3.0-video`, `wan3.0-video-prime`). One unified
`input.media[]` array covers every mode:

- **Text-to-video** — video from a text prompt
- **Image-to-video** — from a single starting image, or a first + last frame pair
- **Omni-Reference** — turn any mix of reference **images, videos, and audio** into video, referring
  to each by position in the prompt (`Image 1` / `图1`, `Video 1` / `视频1`, `Audio 1` / `音频1`)
- **Deck / document → video** — feed a `.pptx` / `.pdf` / `.docx` / `.xlsx` / `.txt` / `.md`
  (≤50 pages, ≤100 MB) and a creative-direction prompt
- **Web page → video** — feed one public, login-free URL and a creative-direction prompt
- **Video edit** — style change or localized replace on an existing clip
- **Video extend** — continue an existing clip

`wan3.0-video-prime` has the same capabilities as `wan3.0-video` but is much faster end-to-end; the
two models have separate free-call quotas.

Legacy **Wan 2.x** (`wan2.7-*`) is still supported for `wan2.7-videoedit` and older grants — see the
Appendix in `SKILL.md`.

## Setup

### Claude Code
```bash
git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/greggchen308/gc-skills.git
cd gc-skills
git sparse-checkout set qwen-video-gen
mv qwen-video-gen ~/.claude/skills/
export DASHSCOPE_API_KEY="your-dashscope-key"
```
Or download the folder directly and place in `~/.claude/skills/qwen-video-gen`.

Then invoke with `/qwen-video-gen`.

### OpenClaw / Hermes
1. Clone this skill into your agent workspace (path depends on your platform config)
2. Point your agent's skill loader to this folder
3. Set `DASHSCOPE_API_KEY` environment variable where the agent runs

## Configuration

`providers.json` stores:
- API endpoint URL (`api_url` — the workspace-scoped MaaS host; already Wan 3.0-ready)
- `upload_api_base` — global DashScope host for temp file uploads
- Environment variable name for the API key (default: `DASHSCOPE_API_KEY`)
- `models_used` — each model with `expires` and a `free_quota` note (e.g. `"30/30 as of 2026-09-06"`)
- Implementation notes

No hardcoded secrets — all keys come from env vars.

## How It Works

1. **Upload** (only for local video / audio / deck / doc inputs) — `scripts/upload_asset.py` uploads
   the file to DashScope temp storage and returns an `oss://` URL valid ~48h. Local images are
   base64-inlined instead; public `https://` URLs pass straight through.
2. **Submit** — `scripts/submit_video.py` POSTs the request spec, gets back a `task_id`. It adds the
   `X-DashScope-OssResourceResolve: enable` header automatically when a media URL is an `oss://` URL.
3. **Poll** — `scripts/check_video.py` polls task status until `SUCCEEDED`, `FAILED`, or `UNKNOWN`
   (`UNKNOWN` = the 24h result window expired — re-submit).
4. **Deliver** — on success, either downloads the video locally or writes the signed URL to a file,
   per your choice (see below). The success output also carries a `usage` block
   (duration, fps, resolution).

See `SKILL.md` for the full mode-by-mode execution guide.

## Local File vs. Hosted Link

Before each job, the skill asks which delivery mode you want:

- **Local file** — downloads the video and reports only the local path.
- **Hosted link** — keeps the provider's signed URL instead of downloading.

Either way, the raw signed URL is **never printed directly to chat/tool-output as a bare string**.
Some agent runtimes — confirmed on OpenClaw
([openclaw/openclaw#112839](https://github.com/openclaw/openclaw/issues/112839)) — hard-truncate long
tool-output strings, which cuts a signed URL through its `OSSAccessKeyId`/`Signature` query params
and makes it unusable. So `check_video.py` writes the URL to a file (`--url-file`) rather than
stdout, and the skill reads that file itself before showing you the link. If you pick the
hosted-link option you'll also see a heads-up about this — shown on every platform, since the skill
can't detect which runtime it's running under.

```bash
# Upload a local asset (deck / clip / voice) -> oss:// URL
python3 scripts/upload_asset.py <local_file> <api_key_env> <model_name> [--api-base=https://dashscope.aliyuncs.com]

# Submit
python3 scripts/submit_video.py <spec.json>

# Poll — local file
python3 scripts/check_video.py <task_id> <api_key_env> <base_url> --mode=download --output-path=<path>
# Poll — hosted link
python3 scripts/check_video.py <task_id> <api_key_env> <base_url> --mode=link --url-file=<path>
```

## Requirements

- Python 3 (stdlib only — no third-party packages)
- `DASHSCOPE_API_KEY` environment variable set
- Network access to the DashScope endpoints

## Model Expiry & Quota Tracking

`providers.json` includes an `expires` date and a `free_quota` note per model. If a model expires
within 7 days, the skill warns you ("⚠️ wan3.0-video expires 2026-11-05 — 5 days left"). `free_quota`
is a manual note — update it yourself when you know the new count.

## See Also

- `SKILL.md` — Detailed execution guide (Wan 3.0 modes + Wan 2.x legacy appendix)
- `providers.json` — API endpoints, model names, expiry & quota tracking
- `scripts/upload_asset.py` — Upload a local file, get a 48h `oss://` URL
- `scripts/submit_video.py` — Submit async video job
- `scripts/check_video.py` — Poll job status and deliver result (download or link)

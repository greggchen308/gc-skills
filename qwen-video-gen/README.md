# qwen-video-gen

Async video synthesis via DashScope/Qwen video-generation APIs.

## What It Does

- **Text-to-video (t2v)** — Generate video from a text prompt
- **Image-to-video (i2v)** — Generate video from a single image or image pair (first frame, first+last frame)
- **Reference-based (r2v)** — Generate video using multiple reference images
- **Video extension** — Extend an existing video clip with new content
- **Video editing** — Apply style changes or localized replacements to existing video
- **Audio-driven** — Generate video synchronized to audio input

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
- API endpoint URL
- Environment variable name for the API key (default: `DASHSCOPE_API_KEY`)
- List of available models with expiry dates
- Implementation notes

No hardcoded secrets — all keys come from env vars.

## How It Works

1. **Submit** — `scripts/submit_video.py` POSTs a request spec to DashScope, gets back a `task_id`
2. **Poll** — `scripts/check_video.py` polls the task status until `SUCCEEDED` or `FAILED`
3. **Deliver** — on success, either downloads the video locally or writes the signed URL to a file, per your choice (see below)

The skill handles all 8 request shapes (per mode) internally. See `SKILL.md` for full execution details.

## Local File vs. Hosted Link

Before each job, the skill asks which delivery mode you want:

- **Local file** — downloads the video and reports only the local path.
- **Hosted link** — keeps the provider's signed URL instead of downloading.

Either way, the raw signed URL is **never printed directly to chat/tool-output as a bare string**. Some agent runtimes — confirmed on OpenClaw ([openclaw/openclaw#112839](https://github.com/openclaw/openclaw/issues/112839)) — hard-truncate long tool-output strings at a fixed character count, which cuts a signed URL through its `OSSAccessKeyId`/`Signature` query params and makes it unusable. So `check_video.py` writes the URL to a file (`--url-file`) rather than stdout, and the skill reads that file itself before showing you the link. If you pick the hosted-link option, you'll also see a heads-up about this — shown on every platform, since the skill can't detect which runtime it's running under.

`check_video.py` usage:
```bash
# Local file
python3 scripts/check_video.py <task_id> <api_key_env> <base_url> --mode=download --output-path=<path>
# Hosted link
python3 scripts/check_video.py <task_id> <api_key_env> <base_url> --mode=link --url-file=<path>
```

## Requirements

- Python 3 (for scripts)
- `DASHSCOPE_API_KEY` environment variable set
- Network access to DashScope endpoint

## Model Expiry Tracking

`providers.json` includes expiry dates for each model. If a model expires within 7 days, the skill will warn you ("⚠️ wan2.7-t2v expires 2026-07-26 — 4 days left").

## See Also

- `SKILL.md` — Detailed execution guide for all modes, request shapes, and delivery modes
- `providers.json` — API endpoints, model names, expiry tracking
- `scripts/submit_video.py` — Submit async video job
- `scripts/check_video.py` — Poll job status and deliver result (download or link)

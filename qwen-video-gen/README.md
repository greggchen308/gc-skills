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
3. **Download** — Agent downloads the generated video when ready

The skill handles all 8 request shapes (per mode) internally. See `SKILL.md` for full execution details.

## Requirements

- Python 3 (for scripts)
- `DASHSCOPE_API_KEY` environment variable set
- Network access to DashScope endpoint

## Model Expiry Tracking

`providers.json` includes expiry dates for each model. If a model expires within 7 days, the skill will warn you ("⚠️ wan2.7-t2v expires 2026-07-26 — 4 days left").

## See Also

- `SKILL.md` — Detailed execution guide for all modes and request shapes
- `providers.json` — API endpoints, model names, expiry tracking
- `scripts/submit_video.py` — Submit async video job
- `scripts/check_video.py` — Poll job status and download result

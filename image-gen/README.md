# image-gen

Multimodal image generation, editing, and combining via DashScope/Qwen APIs.

## What It Does

- **Text-to-image** — Generate an image from a text prompt
- **Image edit** — Edit an existing image based on a text instruction
- **Multi-image combine** — Combine multiple input images into one based on a text instruction

## Setup

### Claude Code
```bash
git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/greggchen308/gc-skills.git
cd gc-skills
git sparse-checkout set image-gen
mv image-gen ~/.claude/skills/
export DASHSCOPE_API_KEY="your-dashscope-key"
```
Or download the folder directly and place in `~/.claude/skills/image-gen`.

Then invoke with `/image-gen`.

### OpenClaw / Hermes
1. Clone this skill into your agent workspace (path depends on your platform config)
2. Point your agent's skill loader to this folder
3. Set `DASHSCOPE_API_KEY` environment variable where the agent runs

## Configuration

`providers.json` stores:
- API endpoint URL
- Environment variable name for the API key (default: `DASHSCOPE_API_KEY`)
- List of previously-used model names

No hardcoded secrets — all keys come from env vars.

## How It Works

1. **Local images to data URIs** — Any local file paths are converted to base64 data URIs before sending
2. **API call** — `scripts/call_provider.py` POSTs the request (with images, prompt, parameters) to DashScope
3. **Deliver** — either downloads generated images locally or writes the signed URL(s) to a file, per your choice (see below)

The skill handles image format detection, encoding, and multi-image workflows internally.

## Local File vs. Hosted Link

Before each job, the skill asks which delivery mode you want:

- **Local file** — downloads the image(s) and reports only the local path(s).
- **Hosted link** — keeps the provider's signed URL instead of downloading.

Either way, the raw signed URL is **never printed directly to chat/tool-output as a bare string**. Some agent runtimes — confirmed on OpenClaw ([openclaw/openclaw#112839](https://github.com/openclaw/openclaw/issues/112839)) — hard-truncate long tool-output strings at a fixed character count, which cuts a signed URL through its `OSSAccessKeyId`/`Signature` query params and makes it unusable. So `call_provider.py` writes the URL to a file (`url_files`) rather than stdout, and the skill reads that file itself before showing you the link. If you pick the hosted-link option, you'll also see a heads-up about this — shown on every platform, since the skill can't detect which runtime it's running under.

`call_provider.py` spec JSON takes `"mode": "download"` + `output_paths`, or `"mode": "link"` + `url_files`.

## Parameters

- `size` — Image dimensions (default: `2048*2048`)
- `negative_prompt` — What NOT to include in the image
- `prompt_extend` — Enable for better CJK/multilingual text rendering (default: true)
- `watermark` — Add DashScope watermark (default: false)
- `n` — Number of images to generate (optional)

## Requirements

- Python 3 (for scripts)
- `DASHSCOPE_API_KEY` environment variable set
- Network access to DashScope endpoint
- Disk space for generated images

## Notes

- Local image paths are embedded as data URIs (base64) — no files are uploaded separately
- Output images are saved to the paths you specify (download mode) or referenced via file-written links (link mode)
- Supports PNG, JPG, and other common image formats

## See Also

- `SKILL.md` — Detailed execution guide for all modes, parameters, and delivery modes
- `providers.json` — API endpoints, model names, expiry tracking
- `scripts/call_provider.py` — Submit request and deliver result (download or link)

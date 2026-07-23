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
3. **Download** — Generated images are downloaded from response URLs to your local output paths

The skill handles image format detection, encoding, and multi-image workflows internally.

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
- Output images are saved to the paths you specify
- Supports PNG, JPG, and other common image formats

## See Also

- `SKILL.md` — Detailed execution guide for all modes and parameters
- `providers.json` — API endpoints and model names
- `scripts/call_provider.py` — Submit request and download generated images

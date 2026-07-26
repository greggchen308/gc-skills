---
name: image-gen
description: Provider-agnostic image generation, image editing, and multi-image combine via any multimodal-generation-style API (DashScope/Qwen and others). Remembers provider URLs, API key env vars, and model names across sessions. Triggers on "/image-gen", "generate an image", "make me an image of", "edit this image", "combine these images into one picture", or any request to call an external image-generation model by API.
---

# image-gen

## Summary
A general-purpose skill for calling image-generation/editing multimodal APIs (Alibaba DashScope/Qwen-Image style APIs, and others Gregg adds later). Handles three modes:
1. **Text-to-image generation** — prompt only.
2. **Image edit** — one input image + a text instruction.
3. **Multi-image combine** — multiple input images + a text instruction.

Provider connection details (API URL, key env var name) and previously-used model names are remembered in `providers.json` next to this file, so Gregg doesn't have to re-paste them every time. Model names still evolve fast, so the skill always allows free-text entry even when suggesting remembered ones.

## Config file
`providers.json` (same folder as this SKILL.md) stores:
```json
{
  "providers": {
    "<provider_label>": {
      "api_url": "https://.../generation",
      "api_key_env": "DASHSCOPE_API_KEY",
      "models_used": [ { "name": "qwen-image-2.0-pro-2026-04-22", "expires": "2026-09-30" }, ... ]
    }
  }
}
```
`provider_label` is a short slug Gregg picks or that's derived from the URL host (e.g. `dashscope-qwen`). Read this file at the start of every invocation.

`expires` is `null` if unknown/no expiry communicated. **Every time you list models for the user, check today's date against `expires` and flag any model expiring within 7 days** ("⚠️ qwen-image-2.0-pro-2026-04-22 expires 2026-07-26 — 4 days left") so Gregg doesn't build around a model about to disappear. (Same convention as `qwen-video-gen`'s `providers.json`.)

## Step-by-step execution

### 1. Provider menu
Read `providers.json`. Present Gregg a menu (via AskUserQuestion):
- One option per configured provider (label + api_url host as the description).
- A final option: **"Add new model provider"**.

**If "Add new model provider"**: ask for the **API location URL**. Then ask what env var name to use for its key (suggest a sensible one derived from the provider, e.g. `DASHSCOPE_API_KEY`). Then run the API key check below. Then create the provider entry in `providers.json` with an empty `models_used` list, and continue to step 2.

**If an existing provider is chosen**: look up its `api_key_env` and run the API key check below (this still runs every time — a stored provider doesn't guarantee the key is currently set in this shell).

**API key check** (applies in both branches):
- Check (without ever printing its value) whether the env var is non-empty: `[ -n "$VARNAME" ] && echo SET || echo MISSING`.
- If missing: guide Gregg to add it himself —
  1. Add a placeholder export line to `~/.zshrc` yourself (Edit tool), e.g. `export DASHSCOPE_API_KEY="YOUR_..._HERE"`.
  2. Tell Gregg to open `~/.zshrc` in TextEdit (`Cmd+Shift+G` → `~/.zshrc`), paste his real key over the placeholder, save.
  3. Never ask him to paste the key into chat. Never print it, even partially.
  4. After he confirms, `source ~/.zshrc` in the same Bash call that runs the actual request (a new/sourced shell picks it up; the current one may not).
- If already set: proceed silently, no need to mention it.

### 2. Model menu
Look up `models_used` for the chosen provider in `providers.json`. Present a menu (via AskUserQuestion), showing each model's name + expiry (flagging anything expiring within 7 days per the Config file section above):
- One option per remembered model.
- **"Add new model"** — ask Gregg to type the model string freely (models evolve fast; never treat the remembered list as exhaustive). Ask if he knows an expiry date for it; store `expires` (or `null`). Append it to `models_used` after a successful call.
- **"Remove a model"** — ask which remembered model to remove (useful when a free-quota/trial model expires or is retired), delete it from `models_used` in `providers.json`, then re-show this same menu so Gregg can pick a model to actually proceed with.

If `models_used` is empty (brand-new provider), skip straight to asking Gregg to type a model — there's nothing to list yet.

### 3. Requirement / subject
If Gregg already described what he wants (as in a prior message), use that. Otherwise ask him to specify the image requirement/subject in plain language.

### 4. Sample cURL (optional, new providers only)
If this is a brand-new provider being added for the first time, ask Gregg if he can provide a sample cURL from the provider's docs for this specific call (generation / edit / combine). If he provides one, use it to cross-check the request shape (headers, body field names, parameter names) — providers vary. If he has none, fall back to the DashScope-style shape already known to this skill (see "Request shapes" below) and say so. Skip this step entirely for a provider already configured in `providers.json` — the shape is already known.

### 5. Mode: generate vs edit vs combine
Determine which of the three modes this is:
- No input images mentioned/provided → **text-to-image generation**.
- One input image + an instruction to modify it → **image edit**.
- Two or more input images + an instruction describing how they interact → **multi-image combine**.
If ambiguous, ask Gregg directly which mode he means.

For edit/combine modes, ask Gregg for the input image(s): accept either a local file path or an already-hosted URL.
- Local path → the helper script (`scripts/call_provider.py`) base64-encodes it into a `data:` URI automatically. No manual upload step needed.
- URL → passed through as-is.

### 6. Image size / aspect ratio
Ask Gregg which aspect ratio: **9:16, 16:9, square, 4:3, or 3:4** (his exact menu). Map to the provider's expected `size` string. For DashScope/Qwen-Image (2048 px on the long edge), use:
| Choice | size string |
|---|---|
| square | `2048*2048` |
| 16:9 | `2048*1152` |
| 9:16 | `1152*2048` |
| 4:3 | `2048*1536` |
| 3:4 | `1536*2048` |

If the provider is not DashScope/Qwen (a new provider Gregg is adding), ask him for the exact size parameter format that provider expects instead of guessing.

### 7. Write the prompt
Write a vivid, specific prompt tailored to the requirement gathered in step 3, in the style/language conventions appropriate to the model provider (e.g. Qwen-Image responds well to richly-detailed English or Chinese prompts with concrete composition, lighting, lens/style cues — mirror whichever language Gregg's requirement was in if it was Chinese, since these models are natively bilingual and prompt fidelity is often better in-language for CJK subject matter).

**Mandatory check:** if the prompt contains Chinese characters, OR the requirement asks for Chinese text/characters to appear rendered in the output image (e.g. calligraphy, signage, a seal/stamp with Chinese text), then `prompt_extend` **must** be set to `true` in the request. (This mirrors the two provided example cURLs, both of which render Chinese text in-image and both set `prompt_extend: true`.)

Show Gregg the prompt before calling the API only if he asked to review it first; otherwise proceed (he can always ask to see it).

### 8. Output destination
Ask Gregg where to save the resulting image(s):
- For Claude Code / Hermes Agent Desktop usage: ask for an absolute local folder/file path. Default to displaying the file back to him with the Read tool after saving (as done previously), unless he says not to.
- For other agent contexts (e.g. OpenClaw) where the invoking agent's job is to push into a frontend messaging channel rather than save to disk: ask whether to save locally, output as a data URI/URL for the calling agent to forward, or both. Don't assume — this skill may be invoked from contexts without a local filesystem the end user can browse.

### 9. Build the request spec and call the script
Write a spec JSON (see script docstring for shape) to a scratch file, then run:
```bash
python3 /Users/GreggChen/.claude/skills/image-gen/scripts/call_provider.py <spec.json>
```
The script:
- base64-encodes any local `input_images` paths into data URIs,
- POSTs to `api_url` with the Bearer key from `api_key_env`,
- downloads returned image URL(s) to `output_paths`,
- prints `{"saved": [...], "request_id": "..."}` on success.

If the provided sample cURL (step 4) implies a different request/response shape than DashScope's, adapt the spec or the script call accordingly — don't force-fit a shape the provider doesn't use. For a genuinely different provider (different field names entirely), note the difference to Gregg and consider it may need a small script variant rather than forcing one script to handle every provider's quirks.

### 10. Confirm and remember
After a successful save:
- Update `providers.json` with any new provider entry / new model name (including `expires` if Gregg gave one).
- Tell Gregg where the file(s) were saved (and display via Read if in a filesystem context).

## Request shape reference (DashScope/Qwen-Image style, default assumption)

**Text-to-image:**
```json
{
  "model": "<model>",
  "input": { "messages": [ { "role": "user", "content": [ { "text": "<prompt>" } ] } ] },
  "parameters": { "negative_prompt": "...", "prompt_extend": true, "watermark": false, "size": "2048*2048" }
}
```

**Image edit** (one input image + text):
```json
{
  "input": { "messages": [ { "role": "user", "content": [
    { "image": "<url or data URI>" },
    { "text": "<edit instruction>" }
  ] } ] }
}
```

**Multi-image combine** (N input images + text):
```json
{
  "input": { "messages": [ { "role": "user", "content": [
    { "image": "<url or data URI 1>" },
    { "image": "<url or data URI 2>" },
    { "text": "<combine instruction>" }
  ] } ] }
}
```
Order matters — the text instruction typically refers to images by position ("图一" = first image, "图二" = second image), so preserve the order Gregg gives input images in.

## Security notes
- Never print, log, or echo API key values, even partially — this previously tripped the permission classifier and is also just good practice.
- Never write API keys into `providers.json` — only the env var *name* is stored there, never the value.
- `providers.json` and any scratch spec files may contain local file paths but should never contain key material.

## Signed URL truncation (platform display-layer bug)
`call_provider.py` already downloads generated images to local `output_paths` and only ever prints `{"saved": [...], "request_id": "..."}` — it never returns the provider's raw signed image URL as a bare string. This matters because some agent runtimes hard-truncate long tool-output strings at a fixed character count (confirmed on OpenClaw, see openclaw/openclaw#112839: `coerceDisplayValue` cuts at 160 chars), which would slice a signed OSS URL through its `OSSAccessKeyId`/`Signature` query params and produce an unusable, unrecoverable link. Keep it this way — never change this script or the skill flow to report a raw image URL directly in chat/tool-output on any platform (Claude Code, Hermes, OpenClaw, or future ones); local path + request_id is the safe pattern.

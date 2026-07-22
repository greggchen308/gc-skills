---
name: qwen-video-gen
description: Generate, extend, or edit video via DashScope/Qwen-style async video-synthesis APIs (Wan2.7 family and others Gregg adds later). Handles text-to-video, image-to-video (first frame, first+last frame, audio-driven), video extension from a clip, multi-reference (r2v) generation, and video editing (style change / localized replace). Triggers on "/qwen-video-gen", "generate a video", "make me a video of", "animate this image", "extend this video", "edit this video style", or any request to call an external video-generation model by API.
---

# qwen-video-gen

## Summary
General-purpose skill for calling DashScope/Qwen-style **async video-generation** APIs. Unlike image generation, every call here is submit-then-poll: you POST a request, get back a `task_id`, and poll a status endpoint until `SUCCEEDED` or `FAILED`. This skill covers 8 request shapes across 6 named modes (see step 5), all under the same `wan2.7-*` model family on DashScope, plus room to add other providers later.

Provider connection details and remembered models (with expiry dates, since these are often time-limited access grants) live in `providers.json` next to this file. Read it at the start of every invocation.

## Config file
`providers.json` stores:
```json
{
  "providers": {
    "<provider_label>": {
      "api_url": "https://.../video-generation/video-synthesis",
      "api_key_env": "DASHSCOPE_API_KEY",
      "models_used": [ { "name": "wan2.7-t2v-2026-06-12", "expires": "2026-09-30" }, ... ],
      "notes": "..."
    }
  }
}
```
`expires` is `null` if unknown/no expiry communicated. **Every time you list models for the user, check today's date against `expires` and flag any model expiring within 7 days** ("⚠️ wan2.7-i2v-2026-04-25 expires 2026-07-26 — 4 days left") so Gregg doesn't build around a model about to disappear.

## Step-by-step execution

### 1. Provider menu
Read `providers.json`. Present a menu (AskUserQuestion): one option per configured provider (label + api_url host), plus **"Add new model provider"**.

**New provider**: ask for the API location URL. Ask what env var name to use for the key (suggest one, e.g. `DASHSCOPE_API_KEY`). Run the API key check below. Create the provider entry with empty `models_used`. Continue to step 2.

**Existing provider**: look up `api_key_env`, run the API key check (every time — a stored provider doesn't guarantee the key is loaded in this shell).

**API key check:**
- `[ -n "$VARNAME" ] && echo SET || echo MISSING` — never print the value.
- If missing but present in `~/.zshrc` already (grep the file, don't cat/print it) — just note it needs sourcing, and `source ~/.zshrc` in the same Bash call as the actual request.
- If truly absent from `~/.zshrc` too: add a placeholder export line yourself (Edit tool), tell Gregg to open `~/.zshrc` in TextEdit (`Cmd+Shift+G` → `~/.zshrc`), paste his real key over the placeholder, save. Never ask him to paste the key into chat. Never print it, even partially.
- If already set in-shell: proceed silently.

### 2. Sample cURL (new providers only)
If this is a brand-new provider, ask Gregg for a sample cURL from the provider's docs for this call. Use it to cross-check request shape (headers, field names). Skip entirely for an already-configured provider — the shape is known (see "Request shapes" below).

### 3. Model menu
Present `models_used` for the chosen provider (name + expiry, flagging anything expiring within 7 days). Menu options:
- One per remembered model.
- **"Add new model"** — free-text entry (models evolve fast). Ask if Gregg knows an expiry date for it; store `expires` (or `null`). Append to `models_used` after a successful call.
- **"Remove a model"** — ask which to remove (for expired free-quota models), delete from `models_used`, then re-show this menu to pick a model to actually proceed with.

If `models_used` is empty, skip straight to free-text model entry.

### 4. Requirement / subject
If Gregg already described what he wants, use that. Otherwise ask him to specify the video requirement/subject in plain language.

### 5. Mode menu
Ask which mode this is (AskUserQuestion, named menu — do not try to infer this from context, the shapes are too different to guess safely):

| Mode | What it needs from Gregg | `input` shape |
|---|---|---|
| **Text-to-video** | Just the prompt (+ optional negative_prompt, + optional audio_url for custom soundtrack) | `{"prompt": "...", "negative_prompt"?: "...", "audio_url"?: "..."}` |
| **Image-to-video (first frame)** | Prompt + one starting image (local path or URL) | `{"prompt": "...", "media": [{"type": "first_frame", "url": "..."}]}` |
| **Image-to-video (first + last frame)** | Prompt + start image + end image | `{"prompt": "...", "media": [{"type":"first_frame","url":"..."},{"type":"last_frame","url":"..."}]}` |
| **Image-to-video (audio-driven)** | Prompt + starting image + a driving audio file (e.g. singing/speech to lip-sync to) | `{"prompt": "...", "media": [{"type":"first_frame","url":"..."},{"type":"driving_audio","url":"..."}]}` |
| **Extend an existing video** | Prompt describing what happens next + the source clip | `{"prompt": "...", "media": [{"type": "first_clip", "url": "..."}]}` |
| **Reference-driven (r2v)** | Prompt referring to inputs by position ("图一"/"视频1" etc.) + 1+ reference images/videos, each optionally with a `reference_voice` audio clip | `{"prompt": "...", "media": [{"type":"reference_image"|"reference_video","url":"...","reference_voice"?:"..."}, ...]}` |
| **Video edit — style change** | Instruction (e.g. "convert to claymation style") + the source video, no reference image | model `wan2.7-videoedit`; `{"prompt": "...", "media": [{"type": "video", "url": "..."}]}` |
| **Video edit — localized replace** | Instruction (e.g. "replace her outfit with the one in this image") + source video + one reference image | model `wan2.7-videoedit`; `{"prompt": "...", "media": [{"type":"video","url":"..."},{"type":"reference_image","url":"..."}]}` |

For any mode requiring media, ask for each input file: local path or already-hosted URL. Local paths get base64-encoded into `data:` URIs by the skill before sending (mirror the `to_data_uri_or_url` helper pattern from the image-gen skill — add this conversion inline when building the spec, since `submit_video.py` intentionally does not do it itself, as the `media` array shape varies too much per mode to hardcode centrally).

**r2v ordering matters**: preserve the order Gregg gives reference images/videos, since the prompt refers to them by position (图一 = first, 图二 = second, 视频1 = first video, etc.).

### 6. Video size / aspect ratio
Ask: **9:16, 16:9, square, 4:3, or 3:4**. Map directly to the `ratio` parameter string (DashScope Wan2.7 takes ratio as literally `"16:9"`, `"9:16"`, `"1:1"` for square, `"4:3"`, `"3:4"` — confirmed working with `"3:4"` in this session). Some modes (image-to-video with first+last frame, video edit) may not need/accept a `ratio` parameter since the frame dimensions are implied by the input media — check the sample cURLs for that mode; omit `ratio` if the reference shape doesn't include it.

Also ask Gregg for **duration** if not already implied (default 10s unless he specifies otherwise; confirmed workable values include 10 and 15).

### 7. Write the prompt
Write a vivid, specific prompt in the style/language appropriate to the mode and content:
- Mirror Gregg's language (English or Chinese) — these models are natively bilingual, and prompt fidelity for CJK subject matter is often better in-language.
- For r2v mode, structure the prompt to reference inputs by position per the convention above.
- For video-edit mode, keep the prompt to a clear, short instruction — these aren't scene descriptions, they're edit commands.

**Mandatory parameter rule:** if the prompt contains Chinese characters, OR spoken/sung dialogue in the video is Chinese (e.g. driving_audio, r2v dialogue), OR any on-screen Chinese text is expected → `prompt_extend` **must** be `true`. `watermark` defaults to `false` unless Gregg asks for it on (note: several of the provider's own sample cURLs default `watermark: true` — always set it explicitly rather than omitting it, don't rely on the provider's default).

Show the prompt before calling only if Gregg asked to review it first.

### 8. Output destination
Ask where Gregg wants the result:
- **Claude Code / Hermes Agent Desktop**: link only by default (per Gregg's standing preference) — do not auto-download the video file. Offer local download as an explicit opt-in if he asks for it later, since the signed `video_url` expires (~24h observed).
- **Other agent contexts** (e.g. OpenClaw): ask whether to output the link for the invoking agent to forward to a frontend messaging channel, save locally, or both — don't assume, this skill may run somewhere with no local filesystem the end user can browse.

### 9. Build the request spec and submit
Write a spec JSON to a scratch file:
```json
{
  "api_url": "<provider api_url>",
  "api_key_env": "<provider api_key_env>",
  "model": "<chosen model>",
  "input": { ... built per mode table in step 5 ... },
  "parameters": {
    "resolution": "720P",
    "ratio": "<mapped ratio, omit if mode doesn't use it>",
    "duration": <int>,
    "prompt_extend": <bool per step 7 rule>,
    "watermark": <bool>
  }
}
```
Run:
```bash
source ~/.zshrc 2>/dev/null
python3 /Users/GreggChen/.claude/skills/qwen-video-gen/scripts/submit_video.py <spec.json>
```
This prints `{"task_id": "...", "task_status": "PENDING", "request_id": "..."}` on success, or exits non-zero with the provider's error on failure (e.g. `InvalidParameter: Field required: input.media` — the classic sign a mode was picked without the media it needs).

### 10. Poll until done
Use **ScheduleWakeup** to poll — do not block synchronously waiting minutes for a video job (matches this skill's actual observed behavior: t2v took ~77s, i2v-with-no-media failed instantly).

Each wakeup:
```bash
source ~/.zshrc 2>/dev/null
python3 /Users/GreggChen/.claude/skills/qwen-video-gen/scripts/check_video.py <task_id> <api_key_env> <api_url_host_root>
```
where `<api_url_host_root>` is the provider's `api_url` with the path stripped back to the host (e.g. `https://llm-pke1xmem59p5giq5.cn-beijing.maas.aliyuncs.com`) — task status lives on the **same host** as submission, at `/api/v1/tasks/{task_id}`, confirmed in this session. Do not assume a separate global tasks host.

- `PENDING` / `RUNNING` → schedule another wakeup (~120–180s is reasonable; first check can be sooner if the job is typically fast).
- `SUCCEEDED` → `output.video_url` is the signed download link. Report it to Gregg per step 8's chosen destination. **Prefix the completion message with 3 emoji** (Gregg's standing preference for video-ready alerts, e.g. 🎬🎥✨) so it's visually distinct in a busy chat.
- `FAILED` → report `output.code` and `output.message` verbatim. Common cause: wrong mode chosen for a model that requires `input.media` (i2v family) — don't guess a fix, tell Gregg what's missing and offer the mode menu again.

### 11. Confirm and remember
After success: update `providers.json` with any new provider/model entry (including `expires` if Gregg gave one). Tell Gregg the video is ready with the link (3-emoji prefix), and mention if it's a signed URL that will expire.

## Request shape reference (DashScope Wan2.7, confirmed + documented)

All bodies share this envelope:
```json
{
  "model": "<model>",
  "input": { "prompt": "...", "media"?: [...], "negative_prompt"?: "...", "audio_url"?: "..." },
  "parameters": { "resolution": "720P", "ratio"?: "16:9", "duration"?: 10, "prompt_extend": true, "watermark": false }
}
```
See the mode table in step 5 for exact `input.media` shapes per mode. Header is always:
```
X-DashScope-Async: enable
Authorization: Bearer $DASHSCOPE_API_KEY
Content-Type: application/json
```

**Status check:**
```
GET {same host as submission}/api/v1/tasks/{task_id}
Authorization: Bearer $DASHSCOPE_API_KEY
```
Response `output.task_status` ∈ `PENDING | RUNNING | SUCCEEDED | FAILED`. On `SUCCEEDED`, `output.video_url` is a signed OSS URL (observed ~24h-scale expiry via the `Expires` query param — treat as time-limited, not permanent).

## Security notes
- Never print, log, or echo API key values, even partially.
- Never write API keys into `providers.json` — only the env var *name*.
- Scratch spec files may contain local file paths but never key material.
- Signed `video_url` values are time-limited — don't treat them as permanent storage; if Gregg needs durability, download locally on explicit request only.

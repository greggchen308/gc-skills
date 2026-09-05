---
name: qwen-video-gen
description: Generate, extend, or edit video via DashScope/Qwen async video-synthesis APIs. Primary path is the Wan 3.0 family (wan3.0-video / wan3.0-video-prime) with Omni-Reference — turn any mix of image, video, audio, a slide deck / PDF / document, or a public web page into video, plus text-to-video, first-frame and first+last-frame image-to-video, video edit and video extend. Legacy Wan 2.x still supported. Triggers on "/qwen-video-gen", "generate a video", "make me a video of", "animate this image", "extend this video", "edit this video style", "turn this deck into a video", "make a video from this PDF/slides", "animate my presentation", "video from this web page", or any request to call an external video-generation model by API.
---

# qwen-video-gen

## Summary
General-purpose skill for calling DashScope/Qwen-style **async video-generation** APIs. Every call is submit-then-poll: POST a request, get back a `task_id`, poll a status endpoint until `SUCCEEDED` or `FAILED`.

Two model families are supported:
- **Wan 3.0** (`wan3.0-video`, `wan3.0-video-prime`) — the **default, fully-documented path** below. One unified `input.media[]` array with a `type` field covers every mode, including **Omni-Reference** (image / video / audio / slide deck / PDF / doc / web page → video). `wan3.0-video-prime` = same capabilities, much faster end-to-end; each of the two models has its own 30-call free quota.
- **Legacy Wan 2.x** (`wan2.7-*`) — different, older `input` shapes. Only use these when the chosen model is `wan2.7-*`. See the **Appendix — Legacy (Wan 2.x)** at the end.

All mode/parameter guidance in steps 5–9 is **Wan 3.0** unless it says otherwise.

Provider connection details and remembered models (with expiry dates and free-quota notes) live in `providers.json` next to this file. Read it at the start of every invocation.

## Config file
`providers.json` stores:
```json
{
  "providers": {
    "<provider_label>": {
      "api_url": "https://.../video-generation/video-synthesis",
      "api_key_env": "DASHSCOPE_API_KEY",
      "upload_api_base": "https://dashscope.aliyuncs.com",
      "models_used": [
        { "name": "wan3.0-video", "expires": "2026-11-05", "free_quota": "30/30 as of 2026-09-06" }
      ],
      "notes": "..."
    }
  }
}
```
- `expires` is `null` if unknown / no expiry communicated. **Every time you list models, check today's date against `expires` and flag any model expiring within 7 days** ("⚠️ wan3.0-video expires 2026-11-05 — 5 days left").
- `free_quota` is a human note like `"30/30 as of 2026-09-06"` (or `null`). Surface it in the model menu so Gregg knows how many free calls are left. It is **not** auto-decremented — update it by hand in step 11 if he tells you the new count.
- `upload_api_base` is the host for the temp-file-upload credential endpoint (`scripts/upload_asset.py`). It is the **global** DashScope host, not the workspace-scoped MaaS host in `api_url`.

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
If this is a brand-new provider, ask Gregg for a sample cURL from the provider's docs for this call. Use it to cross-check request shape (headers, field names). Skip entirely for an already-configured provider — the shape is known (see "Request shape reference" below).

### 3. Model menu
Present `models_used` for the chosen provider (name + expiry + `free_quota`, flagging anything expiring within 7 days). Menu options:
- One per remembered model. For `wan3.0-video` vs `wan3.0-video-prime`, add a one-liner: **prime is the fast bucket (drafts / iteration), standard is the quality bucket — each has its own 30 free calls.**
- **"Add new model"** — free-text entry (models evolve fast). Ask if Gregg knows an expiry date and/or free quota for it; store `expires` and `free_quota` (or `null`). Append to `models_used` after a successful call.
- **"Remove a model"** — ask which to remove (for expired free-quota models), delete from `models_used`, then re-show this menu.

Do **not** pick a default model — always let Gregg choose. If `models_used` is empty, skip straight to free-text model entry.

### 4. Requirement / subject
If Gregg already described what he wants, use that. Otherwise ask him to specify the video requirement/subject in plain language.

### 5. Mode menu (Wan 3.0)
Ask which mode this is (AskUserQuestion, named menu — do not infer it, the shapes differ too much to guess safely):

| Mode | What it needs from Gregg | `input` shape (Wan 3.0) |
|---|---|---|
| **Text-to-video** | Just the prompt (optional `negative_prompt`) | `{"prompt": "..."}` |
| **Image-to-video (first frame)** | Prompt + one starting image | `{"prompt": "...", "media": [{"type": "first_frame", "url": "..."}]}` |
| **Image-to-video (first + last frame)** | Prompt + start image + end image | `{"prompt": "...", "media": [{"type":"first_frame","url":"..."},{"type":"last_frame","url":"..."}]}` |
| **Omni-Reference** | Prompt that refers to inputs positionally as `Image 1`/`图1`, `Video 1`/`视频1`, `Audio 1`/`音频1` + any mix of: `reference_image` (≤10), `reference_video` (≤5 clips, ≤15s total), `reference_audio` (≤5 clips, ≤15s total) | `{"prompt": "...", "media": [{"type":"reference_image","url":"..."}, {"type":"reference_video","url":"..."}, {"type":"reference_audio","url":"..."}, ...]}` |
| **Deck / document → video** | One `.pptx/.ppt/.pdf/.docx/.doc/.xlsx/.xls/.txt/.md/.key/.pages/.numbers` (≤50 pages, ≤100 MB) + a prompt giving creative direction | `{"prompt": "...", "media": [{"type": "file", "url": "..."}]}` |
| **Web page → video** | One public, login-free URL (news / blog / article) + a prompt giving creative direction | `{"prompt": "...", "media": [{"type": "link", "url": "https://..."}]}` |
| **Video edit** (style change or localized replace) | A short edit-instruction prompt + the source video; for localized replace, also one `reference_image` | `{"prompt": "...", "media": [{"type":"reference_video","url":"..."}]}` (+ optional `{"type":"reference_image","url":"..."}`); set `duration: -1` to preserve length |
| **Video extend** | Prompt describing what happens next + the source clip | `{"prompt": "...", "media": [{"type":"reference_video","url":"..."}]}`; `duration: -1` or an explicit total (input + output ≤ 30s) |

**Mutual-exclusivity rules (Wan 3.0):**
- `first_frame` / `last_frame` **cannot** be combined with any `reference_*` / `file` / `link` in the same request.
- `file` and `link` **cannot** both be present.
- Audio-driven lip-sync (the old Wan 2.7 `driving_audio`) is done in Wan 3.0 through **Omni-Reference**: pass the speech/song as `reference_audio` and describe the lip-sync intent in the prompt ("the person in Image 1 speaks the words in Audio 1").

**Media handling — how each input gets into `media[].url`:**
- **Local image** ≤ 20 MB (`first_frame` / `last_frame` / `reference_image`) → base64-encode into a `data:` URI inline when building the spec (mirror the `to_data_uri_or_url` helper from the image-gen skill). Simplest, no expiry.
- **Local video / audio / file (deck, doc)** → run `scripts/upload_asset.py` first (see step 9a), capture the `oss://…` URL it prints (valid ~48h), and put that in `media[].url`. `submit_video.py` auto-adds the `X-DashScope-OssResourceResolve: enable` header when it sees an `oss://` URL.
- **Already-hosted public `https://` URL** → pass through as-is.

**Omni-Reference ordering matters**: preserve the order Gregg gives inputs *within each type*. The 1st `reference_image` in the array is `Image 1`/`图1`, the 2nd is `Image 2`; the 1st `reference_video` is `Video 1`/`视频1`; the 1st `reference_audio` is `Audio 1`/`音频1`. Images, videos and audio are counted separately, so `Image 1` and `Video 1` can both exist.

### 6. Video size / aspect ratio / duration
- **`ratio`** — ask: `adaptive`, `16:9`, `9:16`, `1:1` (square), `4:3`, `3:4`. Default and recommendation: **`adaptive`** (the model picks from the input media and intent) — especially for Omni-Reference, deck, and mixed-media modes. Use an explicit ratio only when Gregg wants a specific frame.
- **`resolution`** — `480P`, `720P`, or `1080P` (Wan 3.0 default is `1080P`). Recommend **`480P` for drafts/iteration** (faster) and `1080P` for finals. Resolution does not change the 30-call quota.
- **`duration`** — integer seconds `2`–`30`, or **`-1` for smart-duration** (model picks the length from the prompt and media). Recommend `-1` for deck/doc/narrative work; use a small explicit number (e.g. `5`) for quick tests. With a video input, input duration + output duration must be ≤ 30s.

### 7. Write the prompt
Write a vivid, specific prompt in the language/style appropriate to the mode and content:
- Mirror Gregg's language (English or Chinese) — these models are natively bilingual, and CJK subject fidelity is usually better in-language.
- Wan 3.0's prompt budget is **up to 20,000 characters** — longer, structured, shot-by-shot cinematic prompts pay off. Describe camera, lighting, pacing, and any on-screen text.
- **Omni-Reference**: refer to inputs by position — `Image 1` / `图1`, `Video 1` / `视频1`, `Audio 1` / `音频1` (per-type numbering). Example: *"Video 1 sits on the chair from Image 4 and sings the melody in Audio 1; the person from Image 1 walks in holding Image 2."*
- **Video edit**: keep the prompt to a short, clear edit command, not a scene description.
- **Deck / web page → video**: the prompt is creative direction (tone, pacing, style, voiceover feel) layered over the file/link content the model reads.

**Mandatory parameter rules:**
- If the prompt contains Chinese characters, OR spoken/sung dialogue is Chinese, OR any on-screen Chinese text is expected → `prompt_extend` **must** be `true`.
- `audio` (bool, Wan 3.0, default `true`) — output video carries a soundtrack (generated or from reference audio). Set `false` for a silent clip. Pricing is the same either way.
- `watermark` defaults to `false`; always set it explicitly.
- `seed` (int `0`–`2147483647`) — optional; set it when Gregg wants a reproducible re-roll.

Show the prompt before calling only if Gregg asked to review it first.

### 8. Output destination
Ask Gregg (AskUserQuestion) which he wants:
- **Local file** — downloads the video and saves it locally. Ask for an output path (folder or filename); default to a sensible scratch/output location if he doesn't care.
- **Hosted link** — keeps the provider's signed URL instead of downloading. **Always show this warning when offering the link option, regardless of platform**: *"Heads up — some agent runtimes (confirmed on OpenClaw, see openclaw/openclaw#112839) truncate long URLs in tool output, which can break a signed link like this one when copy-pasted. Local file is the safer default if you're not sure this will render fully."* Then respect whichever he picks.

Either way, **never print the raw signed `video_url` directly into chat/tool-output as a bare string.** The truncation bug cuts the URL's query string mid-`Signature`/`OSSAccessKeyId`, leaving an unusable link. If he chooses the link option, the skill still writes the full URL to a small scratch file and reports the file path, never pasting the raw URL into the response.

### 9a. Upload local video / audio / file assets (if any)
For every local `reference_video`, `reference_audio`, or `file` input (and any local image over ~20 MB):
```bash
source ~/.zshrc 2>/dev/null
python3 /Users/GreggChen/.claude/skills/qwen-video-gen/scripts/upload_asset.py <local_path> <api_key_env> <chosen_model> --api-base=<provider upload_api_base>
```
It prints `{"oss_url": "oss://dashscope-instant/.../file.ext", "expires_in_hours": 48, "bytes": N}`. Use `oss_url` verbatim as the `media[].url`. `<chosen_model>` must be the same model you'll generate with (DashScope model-consistency rule). Re-upload if a job is retried more than ~48h later.

### 9b. Build the request spec and submit
Write a spec JSON to a scratch file:
```json
{
  "api_url": "<provider api_url>",
  "api_key_env": "<provider api_key_env>",
  "model": "<chosen model>",
  "input": { ... built per the mode table in step 5; local images as data: URIs, local av/file as oss:// from 9a ... },
  "parameters": {
    "resolution": "480P",
    "ratio": "adaptive",
    "duration": -1,
    "audio": true,
    "prompt_extend": true,
    "watermark": false
  }
}
```
(`seed` optional. `ratio: "adaptive"` is safe to keep for every mode; only drop `ratio` if Gregg explicitly wants the model fully unconstrained. `input` also still accepts a `negative_prompt` string.)
Run:
```bash
source ~/.zshrc 2>/dev/null
python3 /Users/GreggChen/.claude/skills/qwen-video-gen/scripts/submit_video.py <spec.json>
```
This prints `{"task_id": "...", "task_status": "PENDING", "request_id": "..."}` on success, or exits non-zero with the provider's error (e.g. `InvalidParameter: The two modes are mutually exclusive...` — the classic sign that frame + reference types got mixed, see step 5).

### 10. Poll until done
Use **ScheduleWakeup** to poll — do not block synchronously waiting minutes for a video job (observed: t2v ~77s; long / Omni-Reference jobs run several minutes).

Each wakeup, pick the invocation matching Gregg's step 8 choice:
```bash
source ~/.zshrc 2>/dev/null
# Local file:
python3 /Users/GreggChen/.claude/skills/qwen-video-gen/scripts/check_video.py <task_id> <api_key_env> <api_url_host_root> --mode=download --output-path=<output_path>
# Hosted link:
python3 /Users/GreggChen/.claude/skills/qwen-video-gen/scripts/check_video.py <task_id> <api_key_env> <api_url_host_root> --mode=link --url-file=<scratch_url_file_path>
```
where `<api_url_host_root>` is the provider's `api_url` with the path stripped back to the host (e.g. `https://llm-pke1xmem59p5giq5.cn-beijing.maas.aliyuncs.com`) — task status lives on the **same host** as submission, at `/api/v1/tasks/{task_id}`. Pass the same `--mode` and path flag on every poll.

- `PENDING` / `RUNNING` → schedule another wakeup (~120–180s is reasonable; first check can be sooner).
- `SUCCEEDED` (download mode) → script already downloaded the video and printed `{"task_status":"SUCCEEDED","mode":"download","local_path":"...","usage":{...}}`. Report the **local path**. Use the `usage` block (`output_video_duration`, `SR`, `fps`, `ratio`) to tell Gregg what the call produced / consumed.
- `SUCCEEDED` (link mode) → script wrote the signed URL to `<scratch_url_file_path>` and printed `{"task_status":"SUCCEEDED","mode":"link","url_file":"...","usage":{...}}`. Read that file yourself and paste its contents as the link in your response. Repeat the OpenClaw truncation caveat from step 8.
- Either mode: **prefix the completion message with 3 emoji** (Gregg's standing preference, e.g. 🎬🎥✨).
- `FAILED` → report `code` and `message` verbatim. Common cause: mode/media mismatch (see step 5 rules) — don't guess a fix, tell Gregg what's wrong and offer the mode menu again.
- `UNKNOWN` → terminal. The `task_id` is only queryable for 24h and has now expired — the result is gone. Re-submit the job.

### 11. Confirm and remember
After success: update `providers.json` with any new provider/model entry (including `expires` and `free_quota` if Gregg gave them). If Gregg tells you how many free calls are left, update the model's `free_quota` string. Tell Gregg where the result is — local path (download mode) or the link plus expiry caveat (link mode).

## Request shape reference (DashScope Wan 3.0)

All bodies share this envelope:
```json
{
  "model": "wan3.0-video | wan3.0-video-prime",
  "input": { "prompt": "...", "media"?: [ { "type": "...", "url": "..." }, ... ], "negative_prompt"?: "..." },
  "parameters": { "resolution": "480P|720P|1080P", "ratio"?: "adaptive|16:9|9:16|1:1|4:3|3:4", "duration": <2..30 | -1>, "audio"?: true, "seed"?: <int>, "prompt_extend": true, "watermark": false }
}
```
Headers (submission):
```
X-DashScope-Async: enable
Authorization: Bearer $DASHSCOPE_API_KEY
Content-Type: application/json
X-DashScope-OssResourceResolve: enable   ← only when a media url is an oss:// temp URL (submit_video.py adds this automatically)
```

`media[].type` cheat-sheet:

| type | max | notes |
|---|---|---|
| `first_frame` | 1 | strict first frame; not with `reference_*`/`file`/`link` |
| `last_frame` | 1 | strict last frame; not with `reference_*`/`file`/`link` |
| `reference_image` | 10 | `Image N` / `图N` in prompt; JPEG/PNG/BMP/WEBP, ≤20 MB, side [240,8000]px |
| `reference_video` | 5 | `Video N` / `视频N`; mp4/mov, ≤15s total, ≤100 MB/clip |
| `reference_audio` | 5 | `Audio N` / `音频N`; wav/mp3, ≤15s total, ≤15 MB |
| `file` | 1 | docx/doc/xlsx/xls/pptx/ppt/pdf/txt/md/key/pages/numbers, ≤50 pages, ≤100 MB; not with `link` |
| `link` | 1 | one public login-free web page; not with `file` |

Worked example — **Omni-Reference**:
```json
{
  "model": "wan3.0-video",
  "input": {
    "prompt": "Video 1 holds Image 3 and sits on the chair in Image 4, humming the tune in Audio 1. The person from Image 1 walks in holding Image 2 and sets it on the table.",
    "media": [
      { "type": "reference_image", "url": "data:image/png;base64,..." },
      { "type": "reference_video", "url": "oss://dashscope-instant/.../role.mp4" },
      { "type": "reference_image", "url": "https://example.com/prop3.png" },
      { "type": "reference_image", "url": "https://example.com/chair4.png" },
      { "type": "reference_audio", "url": "oss://dashscope-instant/.../tune.mp3" }
    ]
  },
  "parameters": { "resolution": "480P", "ratio": "adaptive", "duration": -1, "prompt_extend": true, "watermark": false }
}
```

Worked example — **deck → video**:
```json
{
  "model": "wan3.0-video",
  "input": {
    "prompt": "Turn this pitch deck into a 30-second product teaser: minimalist, cinematic, cool blue palette, punchy motion-graphic transitions, confident voiceover pacing.",
    "media": [ { "type": "file", "url": "oss://dashscope-instant/.../deck.pptx" } ]
  },
  "parameters": { "resolution": "480P", "ratio": "adaptive", "duration": -1, "prompt_extend": true, "watermark": false }
}
```

**Status check:**
```
GET {same host as submission}/api/v1/tasks/{task_id}
Authorization: Bearer $DASHSCOPE_API_KEY
```
Response `output.task_status` ∈ `PENDING | RUNNING | SUCCEEDED | FAILED | UNKNOWN`. On `SUCCEEDED`, `output.video_url` is a signed OSS URL (~24h expiry) and a top-level `usage` object is returned (`video_count`, `duration`, `input_video_duration`, `output_video_duration`, `fps`, `SR`, `ratio`). `check_video.py` never returns `video_url` as a bare stdout string in either delivery mode (see "Signed URL truncation").

## Security notes
- Never print, log, or echo API key values, even partially.
- Never write API keys into `providers.json` — only the env var *name*.
- Scratch spec files may contain local file paths and base64 image data but never key material.
- `oss://` temp URLs from `upload_asset.py` are account-scoped and expire in ~48h — fine to keep in a scratch spec, not something to publish.

## Signed URL truncation (platform display-layer bug)
Gregg chooses **local file** or **hosted link** per job (step 8) — a real tradeoff (disk vs. durability), not a fake choice. But the raw signed `video_url` must never be printed to stdout as a bare string in *either* mode: some agent runtimes hard-truncate long tool-output strings at a fixed character count (confirmed on OpenClaw, openclaw/openclaw#112839: `coerceDisplayValue` cuts strings at 160 chars). Signed OSS URLs run 250–400+ chars with the auth signature near the end — truncation slices through it, producing a link that returns `InvalidAccessKeyId` and can't be reconstructed.

`check_video.py` handles this by writing the URL to a file (`--url-file`) instead of printing it, regardless of mode. When reporting a link result, always repeat the truncation warning from step 8. Do not assume "Claude Code is safe, so skip the warning" — keep it uniform across platforms per Gregg's explicit preference.

---

## Appendix — Legacy (Wan 2.x)

Use this section **only when the chosen model is `wan2.7-*`**. Wan 2.x uses different, per-mode `input` shapes and older defaults. Everything above (steps 5–9, the Wan 3.0 request reference) does **not** apply to these models.

**Legacy mode table:**

| Mode | `input` shape (Wan 2.x) |
|---|---|
| Text-to-video | `{"prompt": "...", "negative_prompt"?: "...", "audio_url"?: "..."}` |
| Image-to-video (first frame) | `{"prompt": "...", "media": [{"type": "first_frame", "url": "..."}]}` |
| Image-to-video (first + last frame) | `{"prompt": "...", "media": [{"type":"first_frame","url":"..."},{"type":"last_frame","url":"..."}]}` |
| Image-to-video (audio-driven) | `{"prompt": "...", "media": [{"type":"first_frame","url":"..."},{"type":"driving_audio","url":"..."}]}` |
| Extend an existing video | `{"prompt": "...", "media": [{"type": "first_clip", "url": "..."}]}` |
| Reference-driven (r2v) | `{"prompt": "...", "media": [{"type":"reference_image"|"reference_video","url":"...","reference_voice"?:"..."}, ...]}` |
| Video edit — style change | model `wan2.7-videoedit`; `{"prompt": "...", "media": [{"type": "video", "url": "..."}]}` |
| Video edit — localized replace | model `wan2.7-videoedit`; `{"prompt": "...", "media": [{"type":"video","url":"..."},{"type":"reference_image","url":"..."}]}` |

**Legacy defaults / notes:**
- Prompt budget ~5,000 chars (`wan2.7-t2v`). `parameters.resolution` was typically `"720P"`; `duration` confirmed workable at `10` and `15`. No `audio` / `seed` / `-1` smart-duration.
- `ratio` takes literal strings `"16:9"`, `"9:16"`, `"1:1"`, `"4:3"`, `"3:4"`; some modes (first+last frame, video edit) imply frame dims — omit `ratio` if the mode's sample cURL doesn't include it.
- Local media: base64 `data:` URIs inline (the Wan 2.x flow never used `upload_asset.py` / `oss://`).
- r2v ordering: `图一` = first reference, `图二` = second, `视频1` = first video, etc.
- `prompt_extend` must be `true` for any Chinese text/dialogue, same as Wan 3.0.

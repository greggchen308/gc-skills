# gc-skills

A personal collection of **agent skills** — self-contained folders that a `SKILL.md`-aware
runtime (Claude Code, WorkBuddy, OpenClaw, Hermes) can load on demand. Each skill bundles
the runbook the agent follows (`SKILL.md`), human documentation (`README.md`), and the
small Python helpers that do the actual work.

This is **not a Python package** and there is no CLI to install. You install a skill by
copying one folder into your agent's skills directory. This file is the map; each skill's
own README is the detailed documentation.

## Skills

| Skill | What it does | Backend |
| --- | --- | --- |
| [`image-gen`](./image-gen/README.md) | Text-to-image, single-image edit, multi-image combine; remembers providers and used models | DashScope/Qwen-style multimodal generation API |
| [`qwen-video-gen`](./qwen-video-gen/README.md) | Async video synthesis: Wan 3.0 text/image-to-video, Omni-Reference (image/video/audio), deck/doc/web-page → video, video edit and extend; Wan 2.x legacy appendix | DashScope/Qwen async video-synthesis API |
| [`video-trim`](./video-trim/README.md) | Cut one or more time ranges out of a video and stitch the kept segments into one file; lossless stream copy or frame-accurate re-encode | Local `ffmpeg` / `ffprobe`, no network |
| [`meralion-transcribe`](./meralion-transcribe/README.md) | Cloud speech-to-text, plus a chunked cross-check workflow for long/noisy recordings and an Apple Silicon fallback needing no `ffmpeg` | MERaLiON cloud ASR (`api.meralion.ai`) |
| [`workbuddy-insights`](./workbuddy-insights/README.md) | Evidence-based "What I did with WorkBuddy" retrospective, rendered as one branded HTML file | Local WorkBuddy state under `~/.workbuddy-ai/` |

`meralion-transcribe` and `workbuddy-insights` also ship 简体中文 READMEs
([transcribe](./meralion-transcribe/README.zh-CN.md),
[insights](./workbuddy-insights/README.zh-CN.md)).

Invoke with `/image-gen`, `/qwen-video-gen`, `/video-trim`, `/meralion-transcribe`, or
`/workbuddy-insights` — or just describe the task in plain language. The `description`
frontmatter in each `SKILL.md` lists its trigger phrases.

## Install

Install a single skill with a sparse checkout (replace `<skill>` with a folder name):

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/greggchen308/gc-skills.git
cd gc-skills
git sparse-checkout set <skill>
mkdir -p ~/.claude/skills/
mv <skill> ~/.claude/skills/
```

Or clone normally and copy the folders you want, or download a folder directly. With
WorkBuddy you can also say: *"Install `<skill>` skill from
https://github.com/greggchen308/gc-skills/tree/main/`<skill>`"*.

Install roots differ by runtime — use whichever your agent's skill loader reads:

| Runtime | Skills directory used in this repo's docs |
| --- | --- |
| Claude Code | `~/.claude/skills/` |
| WorkBuddy | `~/.workbuddy-ai/skills/` (or the one-line install above) |
| OpenClaw / Hermes | your agent workspace path; point the skill loader at the folder |

## Requirements and credentials

| Skill | Credential | Local tooling |
| --- | --- | --- |
| `image-gen` | `DASHSCOPE_API_KEY` | Python 3 |
| `qwen-video-gen` | `DASHSCOPE_API_KEY` | Python 3 |
| `video-trim` | none | Python 3, `ffmpeg` + `ffprobe` on `PATH` |
| `meralion-transcribe` | MERaLiON API key | Python 3, `ffmpeg` / `ffprobe` — or native macOS `afconvert` / `afinfo` / `python3` / `security` |
| `workbuddy-insights` | none | `sqlite3`, WorkBuddy local state |

Every bundled script uses the **Python standard library only** — no `pip install` anywhere.

- **No secrets are committed.** `providers.json` stores the *name* of the API-key env var,
  never the value. `image-gen` and `qwen-video-gen` check that the variable is set without
  printing it.
- **MERaLiON key handling:** `SKILL.md` reads it from the macOS Keychain service label
  `meralion.ai`, falling back to `MERALION_KEY`. The bundled scripts differ —
  `chunked_asr.py` reads `MERALION_KEY` directly, while `test_meralion.py` calls
  `/usr/bin/security`. Export the variable before running `chunked_asr.py`.
- **Endpoints are account-specific.** The `api_url` in both `providers.json` files is a
  workspace-scoped MaaS host; `qwen-video-gen` also has a separate global
  `upload_api_base` for temp uploads. Replace these with your own endpoints.
- **Model lists are snapshots, not ground truth.** `models_used` records `expires` and
  `free_quota` notes, and the skills flag models expiring within 7 days. Several recorded
  expiry dates have since passed — verify against your provider and use the skill's
  "Add new model" / "Remove a model" flow rather than assuming the list is current.

## Conventions across the skills

- `SKILL.md` starts with `name` + a `description` full of trigger phrases; the body is a
  numbered runbook for the agent, including what to ask the user and what to verify.
- Helpers in `scripts/` take a JSON spec file or CLI args and print one JSON result line.
  They are intentionally thin — the agent builds the spec, the script executes it.
- **Local file vs hosted link:** the two generation skills ask on every job whether to
  download the result or keep the provider's signed URL. In both cases the raw signed URL
  is written to a file and never printed bare to stdout, because some runtimes truncate
  long tool output ([openclaw/openclaw#112839](https://github.com/openclaw/openclaw/issues/112839)).
  The hosted-link option always carries that heads-up.
- Vendor behaviour is recorded as **dated field notes**, including corrections to earlier
  wrong claims — see [`meralion-transcribe/CHANGELOG.md`](./meralion-transcribe/CHANGELOG.md).
  Two response schemas, silent transcript omissions, and model fallbacks are all
  documented there with the measurements that produced them.

A skill folder looks like this:

```
<skill>/
├── SKILL.md             agent runbook (frontmatter: name + triggers)
├── README.md            human docs (EN; some also README.zh-CN.md)
├── providers.json       optional: endpoints, key env-var names, remembered models
└── scripts/*.py         optional: stdlib-only helpers
```

## Before reusing these elsewhere

This is a working personal collection, not a portable library. The parts that do not
generalize:

- `image-gen`, `qwen-video-gen` and `video-trim` call their scripts through hardcoded
  absolute paths like `/Users/GreggChen/.claude/skills/...`, address the user by name,
  and one assumes `ffmpeg` at `/usr/local/bin/ffmpeg`. Rewrite these for your machine.
- The runbooks name runtime-specific tools — `AskUserQuestion`, `ScheduleWakeup` (for
  async video polling), `present_files` (for the HTML report). Other runtimes need the
  flow adapted, not just the paths.
- `workbuddy-insights` reads WorkBuddy's own session DB, artifact index, usage log and
  project memory. It cannot produce its report on a machine without that state.
- Vendor notes (model names, free quotas, ASR quirks) are observations from the author's
  runs, not a stable API contract. Re-check before relying on them.
- There is no repository-wide `LICENSE` file. `meralion-transcribe/README.md` states
  "as-is for personal and educational use"; other skills state no terms. Add a LICENSE
  before redistributing.

## Adding a skill

One folder per skill, following the layout above. Give `SKILL.md` a `name` and a trigger-rich
`description`, document the install target and any credential env var in its README, and
never commit key values — only env-var names. Update the Skills and Requirements tables
in this file; for a bilingual README or a dated correction log, follow the
`meralion-transcribe` example.

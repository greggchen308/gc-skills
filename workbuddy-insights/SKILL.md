---
name: workbuddy-insights
description: Generate an evidence-based "What I did with WorkBuddy" usage review from local state — session DB, artifact index, token accounting and project memory. Use when the user asks for an appraisal/retrospective/self-review of how they've been using WorkBuddy, or wants to know what they actually did over a period. Asks for a time window, computes a deterministic JSON evidence payload (stdlib /usr/bin/python3), and outputs a styled single-file HTML report in official workbuddy.ai brand visual language (mint-green #28b894, Alimama fonts, white/near-white surfaces) with per-claim method provenance.
agent_created: true
---

# WorkBuddy usage appraisal

Produces a "What I did with WorkBuddy" retrospective — the local equivalent of
`github.com/microsoft/What-I-did-with-Cowork`. Every claim is derived from data on
disk; nothing is inferred from conversation context.

**Do not** write the review from memory of the conversation. Re-query the sources each
time — that is the entire value of the skill.

## When to use
- User asks for an appraisal / review / retrospective of their WorkBuddy usage.
- User wants to know "what did I actually do with this tool" over a window.
- Periodic self-check (monthly / quarterly) on tool fluency and adoption gaps.

## Data sources (all local, read-only)

| Source | Path | Yields |
|---|---|---|
| Session DB | `~/.workbuddy-ai/workbuddy.db` (sqlite3) | sessions, session_usage, automations, workspaces |
| Artifact index | `~/.workbuddy-ai/artifact-index/*.json` | every file produced, keyed by session id |
| Usage log | `~/.workbuddy-ai/usage-log.json` | skill + MCP usage dates, active days — **check freshness first, see below** |
| Plans | `~/.workbuddy-ai/plans/*.md` | plan-mode artefacts |
| Teams | `~/.workbuddy-ai/teams/*/config.json` | multi-agent orchestration evidence |
| Project memory | `<project>/.workbuddy-ai/memory/*.md` | narrative of what was done and why |
| Skills | `~/.workbuddy-ai/skills/*/SKILL.md` | what's installed vs used |
| MCP config | `~/.workbuddy-ai/mcp.json` | configured connectors |

### Useful queries

```bash
DB=~/.workbuddy-ai/workbuddy.db
/usr/bin/sqlite3 -header -column $DB "SELECT mode, COUNT(*) n FROM sessions GROUP BY mode ORDER BY n DESC;"
/usr/bin/sqlite3 -header -column $DB "SELECT model, COUNT(*) n FROM sessions GROUP BY model ORDER BY n DESC;"
/usr/bin/sqlite3 -header -column $DB "SELECT COALESCE(expert_id,'(none)') e, COUNT(*) n FROM sessions GROUP BY expert_id ORDER BY n DESC;"
/usr/bin/sqlite3 -header -column $DB "SELECT date(created_at/1000,'unixepoch','+8 hours') d, COUNT(*) n FROM sessions GROUP BY d ORDER BY d;"
/usr/bin/sqlite3 -header -column $DB "SELECT SUM(used) total_tokens, COUNT(*) n FROM session_usage;"
/usr/bin/sqlite3 -header -column $DB "SELECT COUNT(*) FROM automations WHERE deleted_at IS NULL;"
```

Session rows carry: `id, cwd, title, custom_title, mode, model, expert_id, created_at,
last_activity_at`. Join `session_usage.session_id → sessions.id` for tokens (`used`) and
context window (`size`).

Artifact index entries are `{version, lastUpdated, artifacts:[{name, uri, mimeType,
contentType, size, createdAt, _meta:{sourceTool}}]}`. URI is `file://` — percent-decode it.

⚠️ **`usage-log.json` freshness — test it, do not assume.** It was observed frozen on
2026-09-22 (`activeDays` ending `2026-08-18`, only 4 skills tracked, none of them the
window's actually-used ones). **Re-verified 2026-09-29: it is live again** — newest
`activeDays` entry was that same day, and `skills` / `mcps` max `lastUsedDate` were too.
So compare its newest entry against the artifact index / session DB before trusting it.
If it *is* stale, do not derive "skills used" from it at all; read
`~/.workbuddy-ai/skills/*/SKILL.md` plus the session transcripts instead, and report the
staleness itself as a finding (a real platform-hygiene gap, not just an inconvenience).

🐛 **`activeDays` is ordered NEWEST-FIRST.** `d['activeDays'][-1]` is the *oldest* entry,
not the latest — reading it as "last" makes a live file look frozen by weeks. This exact
misread produced a false staleness finding on 2026-09-29. Use `[0]` or `max()` instead.
It also tracks only a **subset** of installed skills (6 tracked vs 22 installed on
2026-09-29), so absence from it is *not* evidence a skill was never used.

## Platform requirements (verified 2026-09-29; re-verified 2026-11-19 with compute.py)

All dependencies are **macOS system binaries with native arm64e slices** — no Homebrew,
no managed runtimes, no Rosetta. Verified on Apple M5 / macOS 27.0.1 (build 26A434):

| Dependency | Status |
|---|---|
| `/usr/bin/sqlite3` (3.54.0) | universal, arm64e — runs natively |
| `/usr/bin/python3` (stdlib `sqlite3`, `json`, `glob`) | universal, arm64e |
| `/usr/bin/grep`, `/usr/bin/find`, `/bin/test`, `/usr/bin/curl` | universal, arm64e |
| All 8 data sources | present |
| `<workspace>/outputs/` | writable |

This matters because the WorkBuddy **managed** Python/Node runtimes are x86_64 and run
under Rosetta after an Intel→Apple-Silicon migration. This skill deliberately uses
absolute `/usr/bin/...` paths and never invokes a managed runtime, so it is **immune to
that whole failure class** — keep it that way. If you ever add a script, make it a shell
script or use `/usr/bin/python3`, never `python3` off a managed path. The bundled
`scripts/compute.py` follows this: **standard library only**, opens the DB read-only
(`file:...?mode=ro`), no third-party imports. Do not "modernise" it.

The 6 documented queries above were re-run against the live schema and all returned rows
— `sessions` and `session_usage` have not drifted. Re-verify with `.schema sessions` if a
query errors; do not assume the skill is broken. Those queries are now for **spot-checking
the payload**, not for producing the report's numbers.

## Deterministic compute payload — no hand arithmetic

Every number printed in the HTML report must be read from the payload produced by
`scripts/compute.py`. Never recompute, estimate, round by hand, or write a figure into
the HTML that is not in the payload. If a figure is missing from the payload, do not
report it. The agent's job is interpretation and narrative, not arithmetic.

```bash
/usr/bin/python3 ~/.workbuddy-ai/skills/workbuddy-insights/scripts/compute.py \
  --window 30 \
  --out "<workspace>/outputs/workbuddy-insights-payload.json"
```

`--window` accepts `all` (legacy first..last behaviour), `30`, `90`, or an inclusive
`YYYY-MM-DD:YYYY-MM-DD` range. Dates use the machine's local timezone. The script
writes atomically, exits non-zero (producing **no** payload) on a missing DB, a schema
error, or a failed internal reconciliation, and never fabricates a value to fill a
silent source.

Payload keys: `window`, `source_coverage` (per-source status / records / newest /
freshness), `headline`, `provenance`, `sessions` (atomic grain, one row per session),
`threads` (rule-based baseline), `artifacts` (deduped deliverables + existence flags),
`usage_log`, `inventories` (plans / teams / skills / MCP server **names only** /
project-memory file inventory). `source_coverage` exists so a partial read can be
disclosed rather than silently bridged.

Two built-in honesty guards: `artifacts.missing_on_disk` is a **raw count, not data
loss** (step 5 still requires the two-branch split), and `sessions.last_activity_date`
is reference-only — it is **never** a duration. The payload is a point-in-time snapshot:
token counts for the currently-active session keep growing while the report is being
written, so a re-run of the same window can legitimately differ.

## Before you start — choose the window

Ask **one** question, via `AskUserQuestion`, with a single choice:

> "Which period should this appraisal cover?" → `Last 30 days` / `Last 90 days` /
> `All history` / custom range.

Do **not** stack a second question in the same call (the user's standing preference is
one question at a time). Pass the answer as `--window`. State the resolved window label,
start and end dates in the report. This replaces the old "first..last `created_at`" rule,
which silently widened the denominator every run and made trend claims non-comparable;
use `all` only when the user explicitly picks it. Recurring delivery is a **separate**
question, offered after the report — see "Recurring run" below.

## Method

1. **Run `scripts/compute.py`** with the chosen window, writing
   `<workspace>/outputs/workbuddy-insights-payload.json`. All arithmetic happens here.
2. **Pull the headline counts from `payload.headline`**, not from fresh ad-hoc queries:
   sessions, active days, tokens, modes, models, experts, automations, skills installed.
   Cite the payload `run_id` in Method & caveats so the report is traceable to a snapshot.
3. **Group sessions into work threads.** Start from `payload.threads` — a deterministic
   **rule** baseline keyed on the normalised `cwd`. Any split/merge into topic threads is
   a **judgement** and must be labelled as such (see "Claim provenance"). Note that
   timestamped per-session workspace directories make the raw baseline degenerate (many
   one-session threads); say so rather than presenting it as a clean taxonomy.
4. **Read every project memory file** found via:
   `find <known project dirs> -path "*/.workbuddy-ai/memory/*.md"`
   (`payload.inventories.project_memory.files` is the inventory; the script does not read
   the bodies). These hold the *why* and the *friction* that raw counts cannot show. They
   are the highest-value source in the whole exercise.
5. **Verify the deliverables exist on disk.** `payload.artifacts` already carries
   deduped deliverables and `exists_on_disk` flags cross-checked against the filesystem;
   still inspect the interesting cases with `ls`. An indexed artifact that is missing, or
   a session with scripts but empty results, is a finding — not a footnote. **But
   missing ≠ lost: account for it in two branches.** (a) Trash scratch that was
   *intentionally* discarded, vs (b) deliverables *migrated elsewhere* (e.g. into a
   SiYuan vault) and therefore legitimately no longer at the old path. Verify the
   migration branch independently — query the destination — before writing anything off.
   Report the split, not a single "44 files missing" scare number.
6. **Check for hygiene regressions.** Grep the transcripts and traces for API keys:
   `grep -rl "sk-" ~/.workbuddy-ai/projects ~/.workbuddy-ai/traces`
   Compare against whatever secret-handling standard the user has already set for
   themselves (check `~/.workbuddy-ai/MEMORY.md`). Inconsistency is a finding.
7. **Check configured-vs-live MCPs.** Start from
   `payload.inventories.mcp_servers_configured` (names only — the script never copies
   credentials into the payload), then check whether those tools are actually present in
   the current session's tool list. A configured-but-unloaded server that the user has a
   standing instruction to use is a high-value finding.
8. **Score six dimensions** 0–10: Artifact orientation, Institutional memory, Verification
   discipline, Orchestration, Operational hygiene, Platform surface. Each score needs a
   cited evidence line **and** a method label (`judgement`, citing a `data`/`rule` field).
   No unlabelled scores.
9. **Rank gaps by return on effort**, not by severity. Lead with what is cheap to fix and
   changes output most.
10. **End with ≤5 sequenced actions**, each with an effort tag.

## Anti-sycophancy rules (non-negotiable)

- Do not award a strength without a citable line from the data.
- Flag every inference as an inference. If a causal story (e.g. "craft-first caused the
  retries") is plausible but unproven, say so explicitly in the report body.
- Note post-hoc reasoning risk: it is easy to construct a clean narrative from whatever
  happens to be on disk. State where the narrative is tidier than the evidence.
- Include a "Method & caveats" section listing what was **not** assessed.

## Claim provenance

Every claim in the report carries a **method label**, matching
`payload.provenance.vocabulary`:

| Label | Meaning | Can a model override it? |
|---|---|---|
| `data` | Raw count / row read from a named source by `compute.py` (headline numbers, artifact existence, tokens) | **No** |
| `rule` | Deterministic transform of `data` — currently the `cwd` → thread baseline | Yes, but only as a labelled `judgement` |
| `judgement` | Model interpretation — topic threads, the 4-phase arc, all six 0–10 scores, gap rankings, causal stories | This is the label itself |

**Two-layer hybrid.** A deterministic baseline is produced first, then a review may
confirm or adjust it:

- Review matches the baseline → `AI-confirmed`.
- Review changes it → `AI-reviewed`, with the baseline grade/value preserved and shown
  (e.g. *"3 threads · AI-reviewed [rule said 28]"*), plus the reason.
- A review that contradicts a `data` value → **`review-rejected`**. Keep the baseline, show
  both the proposed and the measured value, and say why it was rejected. Never let a
  narrative quietly overwrite a count.

**Rendering:** each stat card, thread card and score chip shows its method chip, with the
reason and evidence field on hover (`title` or a `<details>`). Method & caveats includes a
"Claim provenance" line with the count of `data` / `rule` / `judgement` claims and the
list of any `review-rejected` items. This is a labelling discipline, not a scoring rubric:
`compute.py` deliberately emits **no** rule-based 0–10 scores, so no score can be
laundered as "measured".

**Causal limit.** These labels describe *how a claim was produced*, not whether it would
have predicted anything in advance. Thread groupings and scores are retrospective
classifications fitted to whatever is on disk — they explain after the fact. Say so where
a clean narrative risks being read as a forecast.

## Recurring run (opt-in, separate question)

After the report is delivered, offer **one** separate question: *"Run this appraisal on a
schedule?"* Only on an explicit yes, create it with `automation_update`. Check
`mode:"list"` first and update an existing appraisal automation rather than creating a
duplicate. Use `scheduleType:"recurring"` with an `rrule` matching the chosen cadence
(e.g. `FREQ=MONTHLY;BYMONTHDAY=1;BYHOUR=9;BYMINUTE=0`), and a **self-contained** prompt
that names the skill path, the window argument and the output path — no schedule text in
the prompt, since future runs will not see this conversation. Keep it a local, read-only
report; no email or external delivery unless separately requested.

## Output

Two files in `<workspace>/outputs/`:

- `workbuddy-insights-payload.json` — the machine-readable snapshot every number comes
  from (written by `compute.py`; keep it as the audit trail).
- `workbuddy-usage-appraisal.html` — the single self-contained HTML report. Render every
  figure from the payload, include the method chips described in "Claim provenance",
  then `present_files` the HTML.

Do not regenerate or reformat a payload by hand, and do not present the raw JSON as the
deliverable — the HTML is the report.

### Visual language — official workbuddy.ai brand
**Light theme only. The brand is mint-green, NOT blue.** Do not use TDesign blue
(`#0052D9`) — that was an earlier guess and is wrong.

Tokens (extracted from workbuddy.ai production CSS, verified 2026-08-28):

```css
--brand:#28b894; --brand-light:#32e6b9; --brand-dark:#22a683;
--brand-tint:#eef9f7; --brand-tint-2:#e3f5ef;
--purple:#6c4dff; --purple-tint:#f0ecff;      /* secondary accent */
--ink:#191a23; --ink-soft:#333; --muted:#666; --muted-2:#858699;
--bg:#f8f9fa; --card:#fff; --line:#e5e5e5; --line-2:#d2d3e0;
--amber:#ed7b2f; --amber-tint:#fdf3e9;        /* under-used  */
--red:#e34d59;   --red-tint:#fdedee;          /* not used    */
--r-card:12px; --r-btn:4px;                   /* cards 12px, buttons near-square 4px */
--shadow:0 2px 8px rgba(25,26,35,.05); --shadow-hover:0 4px 16px rgba(25,26,35,.08);
```
- **Hero:** white (`#fff`) — NOT a gradient band. Mint radial glow behind
  (`rgba(40,184,148,.13)` → transparent), faint dot-grid overlay with `mask-image` fade,
  `border-bottom:1px solid var(--line)`.
- **Type:** display/UI `'Alimama FangYuanTi VF'`; bold headings `'Alimama ShuHeiTi'`;
  body `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC'`.
  Headings use `clamp()` sizing (e.g. `clamp(34px,4.6vw,56px)`), weight 700, tight
  negative tracking. Numerals: `font-variant-numeric: tabular-nums`.
- **Cards:** `background:#fff; border:1px solid #e5e5e5; border-radius:12px;` — hairline
  border and restrained shadow, not heavy elevation. Hover: border → `--brand-light`,
  `translateY(-2px)`, stronger shadow.
- **Stat cards:** 3px left accent bar — mint healthy, amber under-used, red unused.
- **Chips:** `c-mint / c-mint-solid / c-amber / c-red / c-gray / c-purple`, 4px radius,
  tinted bg with dark-tint text.
- **Method chips (provenance):** `m-data` (mint) / `m-rule` (purple) /
  `m-judgement` (amber) / `m-review-rejected` (red), same 4px radius. Each carries a
  `title` with the reason and the evidence field it rests on. These sit next to stat
  numbers, thread cards and score chips — not in a separate legend.
- **Featured card ("case file"):** the site's signature mint-glow border —
  `background-image: linear-gradient(#fff,#fff) padding-box, linear-gradient(180deg,rgba(40,184,148,0),rgba(40,184,148,.08) 8%,rgba(40,184,148,.12) 12%,rgba(40,184,148,0)) border-box;`
- **Charts:** pure CSS bars (`.bar-track` / `.bar-fill[data-w]`), animate width on load.
  Mint gradient for primary threads, blue `alt` and grey `mute` for context.
- **Timeline:** 2px mint→grey gradient rail, white dots with coloured ring; the latest
  phase gets a mint ring-glow `box-shadow:0 0 0 4px rgba(40,184,148,.13)`.
- **Fonts are CDN-linked** (they are ~450KB subsets — do not embed; keep local fallbacks
  in the stack so the file degrades gracefully offline). No other external dependencies.

#### Re-deriving the tokens (if the site changes)
```bash
curl -sL https://www.workbuddy.ai/ -o /tmp/wb.html
grep -oE 'href="//[^"]*\.css[^"]*"' /tmp/wb.html      # asset base + bundle filenames
# download main-*.css + index-*.css from that base, then:
#   grep -oE '#[0-9a-fA-F]{6}' | sort | uniq -c | sort -rn   -> palette
#   grep -oE 'font-family:[^;}]+' | sort | uniq -c           -> type stack
#   grep -oE 'border-radius:[^;}]+' | sort | uniq -c         -> shape
#   grep -oE 'linear-gradient\([^;}]{0,160}'                 -> gradients
```

### Section order
1. Hero + headline stats
2. At a glance (8 stat cards)
3. The arc (4-phase timeline)
4. Where the work went (token bar chart)
5. Work threads (cards)
6. Scorecard (6 dimensions)
7. What's working (ranked, each with an evidence line)
8. Where the leverage is (ranked gaps, each with a concrete fix)
9. Case file (one post-mortem of the most instructive failure)
10. Next 7 days (≤5 sequenced actions)
11. Method & caveats — include the resolved window, payload `run_id`, `source_coverage`
    (what was read and what was partial/stale), the "Claim provenance" counts, and
    what was **not** assessed

## Notes from the 2026-08-28 run
- `sessions.last_activity_at - created_at` is **not** time-worked — several sessions show
  multi-day spans because they were reopened days later. Never report it as duration.
- Artifact index counts *records*, not unique files; de-duplicate by name before counting
  deliverables, and exclude memory files / intermediates / `/tmp` scripts.
- The most valuable single section was the post-mortem of an abandoned session. Abandoned
  work reveals operating patterns that successes hide. Prefer it over another success story.

## Notes from the 2026-09-22 run
- **Reading user prompts out of transcripts: unwrap `<user_query>` inside
  `<system-reminder>` blocks.** A naive parser that filters `<system-reminder>` out will log
  *zero* real user prompts and leave you inferring intent from session titles alone — which
  produces confidently wrong narratives.
- **Never infer intent from two sessions sharing a title.** Two identically-titled sessions
  6 minutes apart looked like abandon-and-retry; the transcripts showed they targeted two
  *different* documents. Read the body before drawing the conclusion.
- `~/.Trash` cannot be listed (`Operation not permitted`), and neither `trash` CLI nor Finder
  automation is available. Probe specific target paths with `test -e` rather than `ls`-ing
  the directory. If the expected sub-dir is absent, record it as a caveat — do not assume
  data loss; verify the surviving project folders directly.
- A single Bash call can die with Exit 137 / SIGTERM mid-command, silently dropping later
  statements in the same call. Re-run as smaller focused calls; the broker *does* recover.
- Modes worth tracking as a trend line: this window was 13 craft / 7 ask / **0 plan** — plan
  mode had dropped out entirely vs the previous run. Report the direction, not just the count.

## Notes from the 2026-11-19 revision

Ported three structural ideas from `microsoft/What-I-did-with-Cowork` (v49) without
importing its ROI/value model, which would break this skill's evidence-only guarantee:
(1) a user-chosen window and opt-in recurring run, (2) a deterministic compute script so
no number is hand-written by the model, (3) provenance labels with a review-rejected
guardrail. The upstream `Cowork-fit` grades, research-anchored time bands, dollar value
and speed multiplier were deliberately **not** adopted — they are external estimates, not
local evidence.

- `scripts/compute.py` is stdlib-only and reads the DB through `sqlite3` (not the
  `sqlite3` CLI). Verified against the live 345-session DB in `all`, `30`, `90` and custom
  window modes; internal reconciliation checks pass.
- The `cwd` thread baseline is degenerate for timestamped per-session workspace folders —
  it produced 141 threads for 345 sessions in `all` mode. That is a known limitation to
  disclose, not a bug to hide; topic merging is a labelled judgement.
- `usage-log.json` was live on 2026-11-19 (newest `activeDays` = 2026-11-19, 20 skills
  tracked vs 55 installed). `compute.py` computes the freshness verdict mechanically —
  use `max()`, never `[-1]`.
- **Mirror:** `github.com/greggchen308/gc-skills/tree/main/workbuddy-insights`. When this
  skill changes, sync `SKILL.md`, `scripts/compute.py` and both READMEs together; the
  mirror had drifted behind the local copy prior to this revision.

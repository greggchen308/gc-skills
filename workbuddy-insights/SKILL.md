---
name: workbuddy-insights
description: Generate an evidence-based "What I did with WorkBuddy" usage review from local state — session DB, artifact index, token accounting and project memory. Use when the user asks for an appraisal/retrospective/self-review of how they've been using WorkBuddy, or wants to know what they actually did over a period. Outputs a styled single-file HTML report in official workbuddy.ai brand visual language (mint-green #28b894, Alimama fonts, white/near-white surfaces).
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
| Usage log | `~/.workbuddy-ai/usage-log.json` | skill + MCP usage dates, active days |
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

## Method

1. **Set the window.** First and last `created_at` in `sessions`. State it in the report.
2. **Pull the headline counts.** Sessions, active days, tokens, modes, models, experts,
   automations, skills installed.
3. **Group sessions into work threads** by `cwd` + topic. Sum tokens per thread. This is a
   judgement call — say so in the caveats.
4. **Read every project memory file** found via:
   `find <known project dirs> -path "*/.workbuddy-ai/memory/*.md"`
   These hold the *why* and the *friction* that raw counts cannot show. They are the
   highest-value source in the whole exercise.
5. **Verify the deliverables exist on disk.** Cross-check artifact-index entries against
   `ls`. An indexed artifact that is missing, or a session with scripts but empty results,
   is a finding — not a footnote.
6. **Check for hygiene regressions.** Grep the transcripts and traces for API keys:
   `grep -rl "sk-" ~/.workbuddy-ai/projects ~/.workbuddy-ai/traces`
   Compare against whatever secret-handling standard the user has already set for
   themselves (check `~/.workbuddy-ai/MEMORY.md`). Inconsistency is a finding.
7. **Check configured-vs-live MCPs.** Read `mcp.json`, then check whether those tools are
   actually present in the current session's tool list. A configured-but-unloaded server
   that the user has a standing instruction to use is a high-value finding.
8. **Score six dimensions** 0–10: Artifact orientation, Institutional memory, Verification
   discipline, Orchestration, Operational hygiene, Platform surface. Justify each with a
   cited evidence line.
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

## Output

Single self-contained HTML file at
`<workspace>/outputs/workbuddy-usage-appraisal.html`, then `present_files` it.

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
11. Method & caveats

## Notes from the 2026-08-28 run
- `sessions.last_activity_at - created_at` is **not** time-worked — several sessions show
  multi-day spans because they were reopened days later. Never report it as duration.
- Artifact index counts *records*, not unique files; de-duplicate by name before counting
  deliverables, and exclude memory files / intermediates / `/tmp` scripts.
- The most valuable single section was the post-mortem of an abandoned session. Abandoned
  work reveals operating patterns that successes hide. Prefer it over another success story.

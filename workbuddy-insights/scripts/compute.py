#!/usr/bin/python3
"""workbuddy-insights -- deterministic evidence payload.

Read-only. Python standard library only. ALWAYS run with /usr/bin/python3.
The WorkBuddy managed runtimes are a different architecture; never invoke this
script with `python3` resolved from a managed path.

    /usr/bin/python3 scripts/compute.py --window 30 \
        --out <workspace>/outputs/workbuddy-insights-payload.json

    --window  all | 30 | 90 | YYYY-MM-DD:YYYY-MM-DD
              `all` = first..last session (legacy behaviour), otherwise the
              window ends today 23:59:59 local and starts N-1 days earlier.
    --out     payload path (written atomically).
    --config  WorkBuddy config root (default ~/.workbuddy-ai).
    --memory-roots  optional extra roots, comma-separated, scanned for
              <root>/**/.workbuddy-ai/memory/*.md.

Every number the HTML report prints MUST come from this payload. Do not
recompute, estimate, or hand-write a figure into the report. If a figure is not
in the payload, do not report it. This script does not read transcripts, does
not compute time-worked (last_activity_at - created_at is NOT a duration), and
does not assign value judgements -- those are the agent's job and must be
labelled as such (see SKILL.md, "Claim provenance").

The payload records per-source coverage so a silent/partial source can be
disclosed rather than silently bridged. Secrets are never copied out of
mcp.json: only server names are emitted.
"""

import argparse
import collections
import glob
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, time as dtime, timedelta
from urllib.parse import unquote, urlparse

SCHEMA_VERSION = 1
LOCAL_TZ = datetime.now().astimezone().tzinfo

# Deliverable exclusions: these are intermediates, memory files or scratch, not
# deliverables. Keep this list explicit -- an invisible heuristic is a finding
# waiting to happen.
EXCLUDE_PATH_PARTS = ("/.workbuddy-ai/memory/", "/__pycache__/", "/node_modules/")
EXCLUDE_PREFIXES = ("/tmp/", "/private/tmp/", "/var/folders/")
EXCLUDE_SUFFIXES = (".tmp", ".log", ".pyc", ".part", ".swp", ".DS_Store")


def iso_local_dt(ms):
    """Epoch milliseconds -> local ISO date string (or None)."""
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(float(ms) / 1000.0, LOCAL_TZ).date().isoformat()
    except (ValueError, OSError, OverflowError):
        return None


def day_bounds_ms(day):
    """Local-date (YYYY-MM-DD) -> (start_ms, end_ms) inclusive."""
    d = datetime.strptime(day, "%Y-%m-%d").date()
    start = datetime.combine(d, dtime.min, tzinfo=LOCAL_TZ).timestamp() * 1000
    end = datetime.combine(d, dtime.max, tzinfo=LOCAL_TZ).timestamp() * 1000
    return start, end


def resolve_window(spec, conn):
    """Return (label, start_day, end_day, start_ms, end_ms)."""
    row = conn.execute("SELECT MIN(created_at), MAX(created_at) FROM sessions").fetchone()
    if not row or row[0] is None:
        sys.exit("compute: sessions table is empty -- refusing to invent a window")
    first_day = iso_local_dt(row[0])
    today = datetime.now(LOCAL_TZ).date().isoformat()

    if spec == "all":
        start_day, end_day = first_day, iso_local_dt(row[1])
    elif spec in ("30", "90"):
        n = int(spec)
        start_day = (datetime.now(LOCAL_TZ).date() - timedelta(days=n - 1)).isoformat()
        end_day = today
    elif ":" in spec:
        start_day, end_day = spec.split(":", 1)
        # validate before use
        datetime.strptime(start_day, "%Y-%m-%d")
        datetime.strptime(end_day, "%Y-%m-%d")
        if start_day > end_day:
            sys.exit("compute: window start is after window end")
    else:
        sys.exit("compute: --window must be all | 30 | 90 | YYYY-MM-DD:YYYY-MM-DD")

    label = ("All history" if spec == "all" else
             "Last %s days" % spec if spec in ("30", "90") else
             "%s to %s" % (start_day, end_day))
    start_ms = day_bounds_ms(start_day)[0]
    end_ms = day_bounds_ms(end_day)[1]
    return {"requested": spec, "label": label, "start": start_day, "end": end_day,
            "basis": "sessions.created_at, local timezone (%s)" % str(LOCAL_TZ)}, start_ms, end_ms


def coverage_entry(name, path, status, records=None, newest=None, note=None):
    return {"source": name, "path": path, "status": status,
            "records": records, "newest": newest, "note": note}


def read_sessions(conn, start_ms, end_ms):
    """One row per session -- the atomic grain. Tokens joined, never inferred."""
    cur = conn.execute(
        """SELECT s.id, s.cwd, COALESCE(NULLIF(s.custom_title,''), s.title, '') AS title,
                  s.mode, s.model, COALESCE(s.expert_id,'(none)') AS expert,
                  s.created_at, s.last_activity_at, s.status,
                  CASE WHEN s.deleted_at IS NULL THEN 0 ELSE 1 END AS deleted,
                  COALESCE(u.used, 0) AS tokens, COALESCE(u.size, 0) AS context_size
             FROM sessions s
             LEFT JOIN session_usage u ON u.session_id = s.id
            WHERE s.created_at BETWEEN ? AND ?
            ORDER BY s.created_at""", (start_ms, end_ms))
    cols = [d[0] for d in cur.description]
    rows = []
    for raw in cur.fetchall():
        r = dict(zip(cols, raw))
        r["date"] = iso_local_dt(r.pop("created_at"))
        # last_activity_at is retained for reference only; NEVER as a duration.
        r["last_activity_date"] = iso_local_dt(r.pop("last_activity_at"))
        r["tokens"] = int(r["tokens"] or 0)
        r["context_size"] = int(r["context_size"] or 0)
        r["cwd"] = r["cwd"] or "(none)"
        rows.append(r)
    return rows


def normalised_thread_key(cwd):
    """Deterministic baseline thread key. Rule, not judgement."""
    if not cwd or cwd == "(none)":
        return "(no working directory)"
    return os.path.basename(os.path.normpath(cwd)) or cwd


def build_threads(sessions):
    """Rule-based grouping by normalised cwd. The agent may split/merge, but
    only as a labelled judgement (see SKILL.md)."""
    buckets = collections.OrderedDict()
    for s in sessions:
        key = normalised_thread_key(s["cwd"])
        b = buckets.setdefault(key, {
            "key": key, "label": key, "method": "rule",
            "rule": "group by basename(normalised cwd)",
            "session_ids": [], "sessions": 0, "tokens": 0,
            "days": set(), "modes": collections.Counter(),
            "cwds": set(), "deleted_sessions": 0,
        })
        b["session_ids"].append(s["id"])
        b["sessions"] += 1
        b["tokens"] += s["tokens"]
        if s["date"]:
            b["days"].add(s["date"])
        b["modes"][s["mode"] or "(unknown)"] += 1
        b["cwds"].add(s["cwd"])
        b["deleted_sessions"] += s["deleted"]
    out = []
    for b in buckets.values():
        b["active_days"] = len(b["days"])
        b["modes"] = dict(b["modes"].most_common())
        b["cwds"] = sorted(b["cwds"])
        del b["days"]
        out.append(b)
    return sorted(out, key=lambda x: (-x["tokens"], -x["sessions"], x["key"]))


def artifact_path(uri):
    if not uri:
        return None
    if uri.startswith("file://"):
        return unquote(urlparse(uri).path)
    return unquote(uri)


def is_excluded(name, path):
    if not name or name.startswith("."):
        return "hidden or unnamed"
    if name.endswith(EXCLUDE_SUFFIXES):
        return "intermediate suffix"
    p = path or ""
    if any(part in p for part in EXCLUDE_PATH_PARTS):
        return "memory / cache / dependency path"
    if any(p.startswith(pre) for pre in EXCLUDE_PREFIXES):
        return "scratch / tmp path"
    return None


def read_artifacts(config, window_session_ids):
    """Deduped deliverables + two-branch missing-accounting inputs."""
    index_dir = os.path.join(config, "artifact-index")
    files = sorted(glob.glob(os.path.join(index_dir, "*.json")))
    records, in_window, errors = 0, 0, []
    seen = {}
    for fp in files:
        sid = os.path.splitext(os.path.basename(fp))[0]
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError) as exc:
            errors.append({"file": os.path.basename(fp), "error": str(exc)})
            continue
        for a in doc.get("artifacts", []) or []:
            records += 1
            if sid not in window_session_ids:
                continue
            in_window += 1
            name = a.get("name") or ""
            path = artifact_path(a.get("uri"))
            reason = is_excluded(name, path)
            rec = {
                "session_id": sid, "name": name, "path": path,
                "size": a.get("size"), "created": iso_local_dt(a.get("createdAt")),
                "source_tool": (a.get("_meta") or {}).get("sourceTool"),
                "excluded_reason": reason,
                "exists_on_disk": bool(path and os.path.exists(path)) if not reason else None,
            }
            # Artifact index counts records, not unique files. Dedup by name.
            dedup_key = name or (path or "unnamed")
            if dedup_key not in seen:
                seen[dedup_key] = rec
    deliverables = [r for r in seen.values() if not r["excluded_reason"]]
    return {
        "index_files": len(files), "records_total": records,
        "records_in_window": in_window, "unique_names": len(seen),
        "excluded": len(seen) - len(deliverables),
        "deliverables": len(deliverables),
        "present_on_disk": sum(1 for r in deliverables if r["exists_on_disk"]),
        "missing_on_disk": sum(1 for r in deliverables if r["exists_on_disk"] is False),
        "dedup_rule": "one record per artifact name (first seen wins); memory/tmp/cache paths excluded",
        "note": ("missing_on_disk is a RAW count, NOT data loss. SKILL.md step 5 "
                 "requires splitting it into intentionally-discarded scratch vs "
                 "deliverables migrated elsewhere, verified at the destination."),
        "read_errors": errors,
        "items": sorted(deliverables, key=lambda r: (r["created"] or "", r["name"])),
    }


def read_usage_log(config, window_end):
    path = os.path.join(config, "usage-log.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError) as exc:
        return {"status": "unreadable", "note": str(exc)}
    days = d.get("activeDays") or []
    newest_day = max(days) if days else None  # activeDays is NEWEST-FIRST; use max(), not [-1]
    skill_dates = [v.get("lastUsedDate") for v in (d.get("skills") or {}).values() if isinstance(v, dict)]
    mcp_dates = [v.get("lastUsedDate") for v in (d.get("mcps") or {}).values() if isinstance(v, dict)]
    newest_skill = max([x for x in skill_dates if x], default=None)
    newest_mcp = max([x for x in mcp_dates if x], default=None)
    lag = None
    if newest_day:
        lag = (datetime.strptime(window_end, "%Y-%m-%d").date()
               - datetime.strptime(newest_day, "%Y-%m-%d").date()).days
    return {
        "status": "read", "active_days_count": len(days),
        "newest_active_day": newest_day, "lag_days_vs_window_end": lag,
        "newest_skill_last_used": newest_skill, "newest_mcp_last_used": newest_mcp,
        "skills_tracked": len(d.get("skills") or {}),
        "mcps_tracked": len(d.get("mcps") or {}),
        "freshness": ("live" if lag is not None and lag <= 2 else
                      "stale" if lag is not None else "unknown"),
        "note": "Tracks a SUBSET of installed skills. Absence is not evidence of non-use.",
    }


def scan_memory_files(roots):
    """Inventory only -- the agent reads the bodies. Never claims completeness."""
    found, scanned = [], 0
    seen_roots = set()
    # Sort shortest-first and skip roots nested under an already-scanned root,
    # otherwise the same memory file is counted several times.
    for root in sorted({os.path.abspath(os.path.expanduser(r)) for r in roots},
                       key=len):
        if not os.path.isdir(root) or any(
                root == r or root.startswith(r + os.sep) for r in seen_roots):
            continue
        seen_roots.add(root)
        scanned += 1
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in
                           ("node_modules", "__pycache__", ".git", "Library", ".Trash")]
            if os.path.basename(dirpath) == "memory" and dirpath.endswith(".workbuddy-ai/memory"):
                for fn in filenames:
                    if fn.endswith(".md"):
                        found.append(os.path.join(dirpath, fn))
    return {"roots_scanned": scanned, "files": sorted(set(found)),
            "note": "Inventory only; roots are explicit, not a whole-home guarantee."}


def main():
    ap = argparse.ArgumentParser(description="workbuddy-insights deterministic payload")
    ap.add_argument("--window", default="all")
    ap.add_argument("--out", required=True)
    ap.add_argument("--config", default=os.path.expanduser("~/.workbuddy-ai"))
    ap.add_argument("--memory-roots", default="")
    args = ap.parse_args()

    config = os.path.abspath(os.path.expanduser(args.config))
    db = os.path.join(config, "workbuddy.db")
    if not os.path.exists(db):
        sys.exit("compute: missing %s -- no payload (refusing to invent numbers)" % db)

    coverage = []
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    except sqlite3.Error as exc:
        sys.exit("compute: cannot open session DB: %s" % exc)

    try:
        window, start_ms, end_ms = resolve_window(args.window, conn)
        sessions = read_sessions(conn, start_ms, end_ms)
        coverage.append(coverage_entry(
            "session DB", db, "read", len(sessions),
            max([s["date"] for s in sessions if s["date"]], default=None),
            "sessions + session_usage joined read-only; atomic grain = one session"))

        automations = conn.execute(
            "SELECT COUNT(*) FROM automations WHERE deleted_at IS NULL").fetchone()[0]
        automations_in_window = conn.execute(
            "SELECT COUNT(*) FROM automations WHERE deleted_at IS NULL AND created_at BETWEEN ? AND ?",
            (start_ms, end_ms)).fetchone()[0]
    except sqlite3.Error as exc:
        sys.exit("compute: schema/query error -- no payload. Re-verify with .schema sessions: %s" % exc)
    finally:
        conn.close()

    ids = {s["id"] for s in sessions}
    artifacts = read_artifacts(config, ids)
    coverage.append(coverage_entry(
        "artifact index", os.path.join(config, "artifact-index"),
        "read" if not artifacts["read_errors"] else "partial",
        artifacts["records_total"], None,
        "%d index files, %d records in window, %d read errors" %
        (artifacts["index_files"], artifacts["records_in_window"], len(artifacts["read_errors"]))))

    usage = read_usage_log(config, window["end"])
    coverage.append(coverage_entry(
        "usage log", os.path.join(config, "usage-log.json"), usage["status"],
        usage.get("active_days_count"), usage.get("newest_active_day"),
        "freshness=%s; %s" % (usage.get("freshness"), usage.get("note", ""))))

    plans = sorted(glob.glob(os.path.join(config, "plans", "*.md")))
    teams = sorted(glob.glob(os.path.join(config, "teams", "*", "config.json")))
    skills = sorted(glob.glob(os.path.join(config, "skills", "*", "SKILL.md")))
    coverage.append(coverage_entry("plans", os.path.join(config, "plans"), "read", len(plans)))
    coverage.append(coverage_entry("teams", os.path.join(config, "teams"), "read", len(teams)))
    coverage.append(coverage_entry("skills", os.path.join(config, "skills"), "read", len(skills)))

    mcp_path = os.path.join(config, "mcp.json")
    mcp_servers = []
    try:
        with open(mcp_path, "r", encoding="utf-8") as fh:
            mcp_servers = sorted((json.load(fh).get("mcpServers") or {}).keys())
        mcp_status = "read"
    except (OSError, ValueError) as exc:
        mcp_status = "unreadable: %s" % exc
    coverage.append(coverage_entry("MCP config", mcp_path, mcp_status, len(mcp_servers),
                                   note="server NAMES only; no credentials emitted"))

    roots = [os.path.expanduser("~/%s" % r) for r in
             ("workbuddy-ai", "Projects", "Desktop", "WorkBuddy AI", "Downloads")]
    roots += [r.strip() for r in args.memory_roots.split(",") if r.strip()]
    roots += [s["cwd"] for s in sessions if s["cwd"] and s["cwd"] != "(none)"]
    memory = scan_memory_files(roots)
    coverage.append(coverage_entry("project memory", "explicit roots", "read",
                                   len(memory["files"]), None, memory["note"]))

    modes = collections.Counter(s["mode"] or "(unknown)" for s in sessions)
    models = collections.Counter(s["model"] or "(unknown)" for s in sessions)
    experts = collections.Counter(s["expert"] for s in sessions)
    active_days = sorted({s["date"] for s in sessions if s["date"]})
    threads = build_threads(sessions)
    total_tokens = sum(s["tokens"] for s in sessions)

    headline = {
        "sessions": len(sessions),
        "active_days": len(active_days),
        "first_day": active_days[0] if active_days else None,
        "last_day": active_days[-1] if active_days else None,
        "total_tokens": total_tokens,
        "sessions_with_usage_row": sum(1 for s in sessions if s["tokens"] > 0),
        "modes": dict(modes.most_common()),
        "models": dict(models.most_common()),
        "experts": dict(experts.most_common()),
        "automations_active_all_time": automations,
        "automations_created_in_window": automations_in_window,
        "skills_installed": len(skills),
        "deleted_sessions_in_window": sum(s["deleted"] for s in sessions),
        "artifact_deliverables_unique": artifacts["deliverables"],
        "artifact_missing_on_disk": artifacts["missing_on_disk"],
        "project_memory_files": len(memory["files"]),
    }

    # Consistency checks. A mismatch means the payload must not be used.
    problems = []
    if sum(t["sessions"] for t in threads) != headline["sessions"]:
        problems.append("thread session counts do not reconcile to headline.sessions")
    if sum(t["tokens"] for t in threads) != headline["total_tokens"]:
        problems.append("thread token counts do not reconcile to headline.total_tokens")
    if sum(modes.values()) != headline["sessions"]:
        problems.append("mode counts do not reconcile to headline.sessions")
    if problems:
        sys.exit("compute: consistency check failed -- no payload: " + "; ".join(problems))

    provenance = {
        "vocabulary": {
            "data": "raw count/row read from a named source by this script",
            "rule": "deterministic transform of data (e.g. cwd -> thread)",
            "judgement": "model interpretation; must be labelled and cite data/rule evidence",
        },
        "headline": {k: {"method": "data", "evidence": "compute.py / " + k}
                     for k in headline},
        "threads": {"method": "rule", "rule": "group by basename(normalised cwd)",
                    "review_allowed": True,
                    "note": "A model may split/merge, but only as a labelled judgement."},
        "scorecard": {"method": "judgement", "baseline_required": False,
                      "note": "No deterministic score is emitted. Every 0-10 score must cite data/rule evidence and be labelled."},
        "override_guard": "A judgement may NOT contradict a `data` value (counts, existence, tokens). If attempted, flag review-rejected and keep the baseline with both values visible.",
    }

    payload = {
        "schema": SCHEMA_VERSION,
        "run_id": datetime.now(LOCAL_TZ).strftime("%Y%m%dT%H%M%S") + "-%d" % os.getpid(),
        "generated_at": datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
        "generator": "/usr/bin/python3 scripts/compute.py (stdlib only, read-only)",
        "window": window,
        "contract": ("All numbers printed in the HTML report must be read from this payload. "
                     "Never recompute, estimate or hand-write a figure. "
                     "last_activity_date is reference-only, NOT a duration."),
        "source_coverage": coverage,
        "headline": headline,
        "provenance": provenance,
        "sessions": sessions,
        "threads": threads,
        "artifacts": artifacts,
        "usage_log": usage,
        "inventories": {
            "plans": [os.path.basename(p) for p in plans],
            "teams": [os.path.relpath(p, config) for p in teams],
            "skills_installed": [os.path.basename(os.path.dirname(p)) for p in skills],
            "mcp_servers_configured": mcp_servers,
            "project_memory": memory,
        },
    }

    out = os.path.abspath(os.path.expanduser(args.out))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".wb-insights-", suffix=".json",
                               dir=os.path.dirname(out))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, out)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    print("compute: wrote %s" % out)
    print("compute: window %s (%s .. %s)" % (window["label"], window["start"], window["end"]))
    print("compute: %d sessions | %d active days | %d tokens | %d threads | %d unique deliverables (%d missing)"
          % (headline["sessions"], headline["active_days"], headline["total_tokens"],
             len(threads), artifacts["deliverables"], artifacts["missing_on_disk"]))
    print("compute: consistency checks PASSED; sources read %d/%d"
          % (sum(1 for c in coverage if c["status"] == "read"), len(coverage)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Bulk pull GexBot historical classic + state endpoints across a date window.

Mirrors the lib/gexbot.js production two-step fetch (presigned URL → blob)
for 11 endpoints (3 classic + 8 state, excluding orderflow which OMEN
already has). Saves each (endpoint × date) as a gzipped JSON file at
backend/data/gex_classic/{cat}/{date}.json.gz or .../gex_state/{cat}/...

Resume-safe: skips dates where the gzipped output already exists.
Hard-stops if any endpoint hits 3 consecutive trading-day failures.
1-second pause between requests (politeness, not parallelized).
Per-attempt JSONL log at backend/data/gex_classic_state_pull_log.jsonl.

Generates a markdown report at
backend/data/gex_classic_state_pull_report.md when complete (or when
a hard-stop trips).
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date as date_type
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pandas_market_calendars as mcal
import requests
from dotenv import load_dotenv

# ---- config ---------------------------------------------------------------
START = date_type(2025, 9, 8)
END = date_type(2026, 4, 28)

ENDPOINTS = [
    ("classic", "gex_full"),
    ("classic", "gex_zero"),
    ("classic", "gex_one"),
    ("state",   "gamma_zero"),
    ("state",   "gamma_one"),
    ("state",   "vanna_zero"),
    ("state",   "vanna_one"),
    ("state",   "charm_zero"),
    ("state",   "charm_one"),
    ("state",   "delta_zero"),
    ("state",   "delta_one"),
]

BASE_URL = "https://api.gex.bot/v2"
TICKER = os.getenv("GEXBOT_TICKER", "ES_SPX")
USER_AGENT = "GexbotPipeline/1.0-bulkpull"

DELAY_BETWEEN_REQUESTS_S = 1.0
RETRY_MAX = 3
RETRY_BACKOFF_BASE_S = 2.0
CONSECUTIVE_DAY_FAIL_LIMIT = 3
PROGRESS_EVERY_N_DAYS = 10

BACKEND = Path(__file__).resolve().parents[2]
CLASSIC_DIR = BACKEND / "data" / "gex_classic"
STATE_DIR = BACKEND / "data" / "gex_state"
LOG_PATH = BACKEND / "data" / "gex_classic_state_pull_log.jsonl"
REPORT_PATH = BACKEND / "data" / "gex_classic_state_pull_report.md"


# ---- utils ----------------------------------------------------------------
def out_path_for(pkg: str, cat: str, d: date_type) -> Path:
    base = CLASSIC_DIR if pkg == "classic" else STATE_DIR
    return base / cat / f"{d.isoformat()}.json.gz"


def get_trading_days(start: date_type, end: date_type) -> list[date_type]:
    nyse = mcal.get_calendar("NYSE")
    sched = nyse.schedule(start_date=str(start), end_date=str(end))
    return [d.date() for d in sched.index]


def fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.2f}{unit}"
        n /= 1024
    return f"{n:.2f}PB"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---- single-endpoint fetch with retries -----------------------------------
def fetch_one(
    pkg: str, cat: str, d: date_type, api_key: str, sess: requests.Session,
) -> dict[str, Any]:
    presigned = f"{BASE_URL}/hist/{TICKER}/{pkg}/{cat}/{d.isoformat()}?noredirect"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    last_err = None
    for attempt in range(RETRY_MAX):
        try:
            r1 = sess.get(presigned, headers=headers, timeout=20)
            # Auth / not-found are NOT retried — they aren't transient.
            if r1.status_code in (401, 403):
                return {
                    "ok": False, "skip_reason": "auth", "attempts": attempt + 1,
                    "detail": f"step1 HTTP {r1.status_code}: {r1.text[:200]}",
                }
            if r1.status_code == 404:
                return {
                    "ok": False, "skip_reason": "no_data_404", "attempts": attempt + 1,
                    "detail": "step1 HTTP 404 (no data for date)",
                }
            if r1.status_code != 200:
                last_err = f"step1 HTTP {r1.status_code}: {r1.text[:200]}"
                time.sleep(RETRY_BACKOFF_BASE_S * (2 ** attempt))
                continue
            try:
                meta = r1.json()
            except ValueError as e:
                last_err = f"step1 non-JSON: {e!r}"
                time.sleep(RETRY_BACKOFF_BASE_S * (2 ** attempt))
                continue
            blob_url = meta.get("url") if isinstance(meta, dict) else None
            if not blob_url:
                return {
                    "ok": False, "skip_reason": "no_url", "attempts": attempt + 1,
                    "detail": f"step1 missing 'url': {str(meta)[:200]}",
                }
            r2 = sess.get(blob_url, timeout=240)
            if r2.status_code != 200:
                last_err = f"step2 HTTP {r2.status_code}"
                time.sleep(RETRY_BACKOFF_BASE_S * (2 ** attempt))
                continue
            raw = r2.content
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                last_err = f"parse: {e!r}"
                time.sleep(RETRY_BACKOFF_BASE_S * (2 ** attempt))
                continue
            # Save gzipped JSON to disk
            out = out_path_for(pkg, cat, d)
            out.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(out, "wt", encoding="utf-8") as f:
                json.dump(payload, f, separators=(",", ":"))
            n_snap = len(payload) if isinstance(payload, list) else None
            keys = None
            if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                keys = sorted(payload[0].keys())
            return {
                "ok": True, "attempts": attempt + 1, "retried": attempt > 0,
                "n_snapshots": n_snap,
                "size_gz": out.stat().st_size,
                "keys": keys,
            }
        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = f"transient {type(e).__name__}: {e!r}"
            time.sleep(RETRY_BACKOFF_BASE_S * (2 ** attempt))
        except requests.RequestException as e:
            last_err = f"requests error: {e!r}"
            time.sleep(RETRY_BACKOFF_BASE_S * (2 ** attempt))
    return {
        "ok": False, "skip_reason": "retries_exhausted", "attempts": RETRY_MAX,
        "detail": last_err or "unknown",
    }


# ---- report builder -------------------------------------------------------
def build_report(
    days_attempted: list[date_type],
    days_completed: list[date_type],
    wall_seconds: float,
    hard_stop: tuple[str, str, str] | None = None,
) -> None:
    """Read the JSONL log + filesystem and write the markdown report.

    Idempotent: rebuilds from disk state, can be run mid-pull or post-pull.
    """
    by_endpoint = {(pkg, cat): {
        "ok_dates": [], "fail_dates": [], "missing_dates": [],
        "retry_succeeded_dates": [], "size_total": 0, "key_signatures": defaultdict(list),
    } for pkg, cat in ENDPOINTS}

    # Read log entries (last entry per (date, pkg, cat) wins)
    last_entry: dict[tuple[str, str, str], dict] = {}
    if LOG_PATH.exists():
        with LOG_PATH.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = (e["date"], e["pkg"], e["cat"])
                last_entry[key] = e

    # Walk filesystem to capture sizes for resumed/skipped files (where log
    # may not have been written this run)
    fs_sizes: dict[tuple[str, str, str], int] = {}
    for pkg, cat in ENDPOINTS:
        ep_dir = out_path_for(pkg, cat, date_type(2000, 1, 1)).parent
        if ep_dir.exists():
            for p in ep_dir.glob("*.json.gz"):
                d = p.stem.split(".")[0]  # strip .json
                fs_sizes[(d, pkg, cat)] = p.stat().st_size

    # Aggregate per endpoint
    for d in days_attempted:
        d_iso = d.isoformat()
        for pkg, cat in ENDPOINTS:
            key = (d_iso, pkg, cat)
            stats = by_endpoint[(pkg, cat)]
            if key in last_entry:
                e = last_entry[key]
                if e.get("ok"):
                    stats["ok_dates"].append(d_iso)
                    stats["size_total"] += e.get("size_gz", fs_sizes.get(key, 0))
                    if e.get("retried"):
                        stats["retry_succeeded_dates"].append(d_iso)
                    if e.get("keys"):
                        sig = tuple(e["keys"])
                        stats["key_signatures"][sig].append(d_iso)
                else:
                    stats["fail_dates"].append({"date": d_iso, "reason": e.get("skip_reason"), "detail": e.get("detail")})
            elif key in fs_sizes:
                # File on disk from a prior run, no log entry this session
                stats["ok_dates"].append(d_iso)
                stats["size_total"] += fs_sizes[key]
            else:
                stats["missing_dates"].append(d_iso)

    # Write report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w") as f:
        f.write("# GexBot historical classic + state — bulk pull report\n\n")
        f.write(f"**Generated:** {now_iso()}\n\n")
        f.write(f"**Window:** {START.isoformat()} → {END.isoformat()}\n")
        f.write(f"**Trading days in window:** {len(days_attempted)}\n")
        f.write(f"**Trading days fully processed by this run:** {len(days_completed)}\n")
        f.write(f"**Ticker:** {TICKER}\n")
        f.write(f"**Endpoints:** {len(ENDPOINTS)} (3 classic + 8 state)\n")
        f.write(f"**Wall clock:** {wall_seconds/60:.1f} minutes ({wall_seconds:.0f} s)\n")
        if hard_stop:
            pkg, cat, reason = hard_stop
            f.write(f"\n> **HARD STOP:** endpoint `{pkg}/{cat}` hit "
                    f"{CONSECUTIVE_DAY_FAIL_LIMIT} consecutive failures. Last reason: {reason}\n")
        f.write("\n## Per-endpoint summary\n\n")
        f.write("| pkg | cat | ok | fail | missing | retried-ok | total gz |\n")
        f.write("|---|---|---:|---:|---:|---:|---:|\n")
        grand_total = 0
        for pkg, cat in ENDPOINTS:
            s = by_endpoint[(pkg, cat)]
            grand_total += s["size_total"]
            f.write(f"| {pkg} | {cat} | {len(s['ok_dates'])} | {len(s['fail_dates'])} | "
                    f"{len(s['missing_dates'])} | {len(s['retry_succeeded_dates'])} | "
                    f"{fmt_bytes(s['size_total'])} |\n")
        f.write(f"| | **total** | | | | | **{fmt_bytes(grand_total)}** |\n")
        f.write(f"\n## Gaps & failures\n\n")
        any_gap = False
        for pkg, cat in ENDPOINTS:
            s = by_endpoint[(pkg, cat)]
            if s["fail_dates"] or s["missing_dates"]:
                any_gap = True
                f.write(f"### {pkg}/{cat}\n\n")
                if s["fail_dates"]:
                    f.write("**Failed (after retries):**\n\n")
                    for fd in s["fail_dates"]:
                        f.write(f"- {fd['date']}: {fd['reason']} — {fd.get('detail','')}\n")
                if s["missing_dates"]:
                    f.write(f"\n**Missing (not attempted this session):** "
                            f"{len(s['missing_dates'])} dates")
                    if len(s["missing_dates"]) <= 20:
                        f.write(f" — {', '.join(s['missing_dates'])}")
                    f.write("\n")
                f.write("\n")
        if not any_gap:
            f.write("None — every endpoint × every trading day succeeded.\n\n")
        f.write("## Schema variations\n\n")
        any_var = False
        for pkg, cat in ENDPOINTS:
            s = by_endpoint[(pkg, cat)]
            sigs = s["key_signatures"]
            if len(sigs) > 1:
                any_var = True
                f.write(f"### {pkg}/{cat} — {len(sigs)} distinct key sets\n\n")
                # Sort signatures by date count (modal first)
                ordered = sorted(sigs.items(), key=lambda kv: -len(kv[1]))
                modal_keys = set(ordered[0][0])
                for i, (sig, dates) in enumerate(ordered):
                    f.write(f"**Variant {i+1}** ({len(dates)} dates) keys: "
                            f"{', '.join(sig)}\n\n")
                    if i > 0:
                        added = sorted(set(sig) - modal_keys)
                        removed = sorted(modal_keys - set(sig))
                        if added: f.write(f"  - added vs modal: {', '.join(added)}\n")
                        if removed: f.write(f"  - removed vs modal: {', '.join(removed)}\n")
                        f.write(f"  - first dates: {', '.join(dates[:5])}"
                                f"{'…' if len(dates) > 5 else ''}\n")
                f.write("\n")
        if not any_var:
            f.write("None detected. Schema (key set on first snapshot) is identical "
                    "across every successfully-pulled day for every endpoint.\n\n"
                    "Note: variation detection only sees keys captured during this run "
                    "(written to JSONL log at fetch time). Files pulled in prior runs "
                    "and skipped by resume have no key entry; if the run was a clean "
                    "first-pass this caveat doesn't apply.\n\n")
        f.write("## Output paths\n\n")
        f.write(f"- Classic: `{CLASSIC_DIR}/{{cat}}/{{date}}.json.gz`\n")
        f.write(f"- State:   `{STATE_DIR}/{{cat}}/{{date}}.json.gz`\n")
        f.write(f"- JSONL audit log: `{LOG_PATH}`\n")
        f.write(f"- This report: `{REPORT_PATH}`\n")


# ---- main loop ------------------------------------------------------------
def main() -> int:
    load_dotenv(BACKEND / ".env")
    api_key = os.getenv("GEXBOT_API_KEY")
    if not api_key:
        print("ERROR: GEXBOT_API_KEY missing from .env", file=sys.stderr)
        return 2

    days = get_trading_days(START, END)
    print(f"START bulk pull at {now_iso()}")
    print(f"  window={START.isoformat()} → {END.isoformat()}")
    print(f"  trading days={len(days)}, endpoints={len(ENDPOINTS)}")
    print(f"  delay={DELAY_BETWEEN_REQUESTS_S}s, retry={RETRY_MAX}, "
          f"hard-stop={CONSECUTIVE_DAY_FAIL_LIMIT} consecutive day-failures/endpoint")
    print(f"  classic dir: {CLASSIC_DIR}")
    print(f"  state dir:   {STATE_DIR}")
    print(f"  log:         {LOG_PATH}")
    print()

    sess = requests.Session()
    consecutive_fail: dict[tuple[str, str], int] = {ep: 0 for ep in ENDPOINTS}
    cum_ok = 0
    cum_fail = 0
    cum_skipped = 0
    start_time = time.time()
    days_completed: list[date_type] = []
    hard_stop: tuple[str, str, str] | None = None

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as logf:
        for di, d in enumerate(days):
            d_iso = d.isoformat()
            day_ok = 0
            day_fail = 0
            day_skipped = 0
            for pkg, cat in ENDPOINTS:
                out = out_path_for(pkg, cat, d)
                if out.exists() and out.stat().st_size > 0:
                    # Resume: pre-existing file. Treat as success but tag skipped.
                    day_ok += 1
                    cum_ok += 1
                    cum_skipped += 1
                    consecutive_fail[(pkg, cat)] = 0
                    entry = {
                        "ts": now_iso(), "date": d_iso, "pkg": pkg, "cat": cat,
                        "ok": True, "skipped_existing": True,
                        "size_gz": out.stat().st_size,
                    }
                    logf.write(json.dumps(entry) + "\n")
                    logf.flush()
                    continue

                result = fetch_one(pkg, cat, d, api_key, sess)
                entry = {"ts": now_iso(), "date": d_iso, "pkg": pkg, "cat": cat, **result}
                logf.write(json.dumps(entry) + "\n")
                logf.flush()
                if result["ok"]:
                    day_ok += 1
                    cum_ok += 1
                    consecutive_fail[(pkg, cat)] = 0
                else:
                    day_fail += 1
                    cum_fail += 1
                    consecutive_fail[(pkg, cat)] += 1
                    if consecutive_fail[(pkg, cat)] >= CONSECUTIVE_DAY_FAIL_LIMIT:
                        hard_stop = (pkg, cat, str(result.get("detail", "unknown")))
                        print(f"\n!!! HARD STOP at {now_iso()} !!!")
                        print(f"  endpoint: {pkg}/{cat}")
                        print(f"  consecutive failures: {consecutive_fail[(pkg, cat)]}")
                        print(f"  last error: {result.get('detail')}")
                        print(f"  date when hard stop triggered: {d_iso}")
                        time.sleep(DELAY_BETWEEN_REQUESTS_S)
                        break

                # politeness pause AFTER each network attempt
                time.sleep(DELAY_BETWEEN_REQUESTS_S)

            days_completed.append(d)

            if hard_stop is not None:
                break

            if (di + 1) % PROGRESS_EVERY_N_DAYS == 0 or (di + 1) == len(days):
                elapsed = time.time() - start_time
                eta_sec = elapsed / (di + 1) * (len(days) - di - 1)
                print(
                    f"[{di+1:>3d}/{len(days)} days] {d_iso} "
                    f"day_ok={day_ok}/11 day_fail={day_fail}/11 "
                    f"cum_ok={cum_ok} cum_fail={cum_fail} skipped_existing={cum_skipped} "
                    f"elapsed={elapsed/60:.1f}m eta={eta_sec/60:.1f}m",
                    flush=True,
                )

    elapsed_total = time.time() - start_time
    print()
    print(f"END at {now_iso()}, elapsed={elapsed_total/60:.1f} minutes")
    print(f"  days completed: {len(days_completed)}/{len(days)}")
    print(f"  cumulative ok: {cum_ok}  fail: {cum_fail}  skipped(pre-existing): {cum_skipped}")
    if hard_stop:
        print(f"  HARD STOP: {hard_stop[0]}/{hard_stop[1]} — {hard_stop[2]}")
    print()
    print("Building report…")
    build_report(days, days_completed, elapsed_total, hard_stop=hard_stop)
    print(f"Report: {REPORT_PATH}")
    return 0 if hard_stop is None else 1


if __name__ == "__main__":
    sys.exit(main())

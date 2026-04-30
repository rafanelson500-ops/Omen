"""Targeted repull for the 7 endpoint-day combos that hit DNS resolution
failures during the 2026-04-30 bulk_pull run.

Reuses bulk_pull.fetch_one() for identical fetch + gzip-on-write semantics.
After each download, verifies file integrity (gzip-decompresses, parses
JSON, confirms it's a non-empty list of dicts).

Appends per-attempt entries to the same JSONL log
(backend/data/gex_classic_state_pull_log.jsonl).
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import time
from datetime import date as date_type
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bulk_pull  # type: ignore

# The 7 missing combos confirmed via on-disk inspection + JSONL log:
MISSING = [
    (date_type(2026, 3, 24), "state",   "vanna_one"),
    (date_type(2026, 3, 24), "state",   "delta_zero"),
    (date_type(2026, 3, 25), "classic", "gex_full"),
    (date_type(2026, 3, 25), "classic", "gex_zero"),
    (date_type(2026, 3, 25), "classic", "gex_one"),
    (date_type(2026, 3, 25), "state",   "gamma_zero"),
    (date_type(2026, 3, 25), "state",   "gamma_one"),
]


def verify_file(path: Path) -> dict:
    """Open the gzipped file, parse JSON, confirm shape. Returns
    {ok: bool, n: int|None, first_ts: int|None, last_ts: int|None,
     size_gz: int, error: str|None}."""
    out = {"ok": False, "n": None, "first_ts": None, "last_ts": None,
           "size_gz": 0, "error": None}
    if not path.exists():
        out["error"] = "file does not exist"
        return out
    out["size_gz"] = path.stat().st_size
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        out["error"] = f"open/parse failed: {e!r}"
        return out
    if not isinstance(data, list):
        out["error"] = f"top-level is {type(data).__name__}, expected list"
        return out
    if len(data) == 0:
        out["error"] = "empty list"
        return out
    out["n"] = len(data)
    if isinstance(data[0], dict):
        out["first_ts"] = data[0].get("timestamp")
        out["last_ts"] = data[-1].get("timestamp")
    out["ok"] = True
    return out


def main() -> int:
    load_dotenv(bulk_pull.BACKEND / ".env")
    api_key = os.getenv("GEXBOT_API_KEY")
    if not api_key:
        print("ERROR: GEXBOT_API_KEY missing from .env", file=sys.stderr)
        return 2

    print(f"REPULL {len(MISSING)} missing endpoint-days at {datetime.now().isoformat(timespec='seconds')}")
    for d, pkg, cat in MISSING:
        print(f"  - {d.isoformat()}  {pkg}/{cat}")
    print()

    sess = requests.Session()
    results = []
    for d, pkg, cat in MISSING:
        out = bulk_pull.out_path_for(pkg, cat, d)
        if out.exists() and out.stat().st_size > 0:
            print(f"  [{pkg}/{cat:<11} {d}] file already on disk (size={out.stat().st_size:,}B); "
                  f"verifying instead of re-downloading")
            v = verify_file(out)
            results.append({"date": d.isoformat(), "pkg": pkg, "cat": cat,
                            "action": "verified_existing", **v})
            continue

        t0 = time.time()
        result = bulk_pull.fetch_one(pkg, cat, d, api_key, sess)
        elapsed = time.time() - t0
        ok = result.get("ok", False)
        # log to the canonical JSONL too (matches bulk_pull format)
        with bulk_pull.LOG_PATH.open("a") as logf:
            entry = {"ts": datetime.now().isoformat(timespec="seconds"),
                     "date": d.isoformat(), "pkg": pkg, "cat": cat,
                     "source": "repull_missing.py", **result}
            logf.write(json.dumps(entry) + "\n")
            logf.flush()

        if not ok:
            print(f"  [{pkg}/{cat:<11} {d}] FETCH FAILED in {elapsed:.1f}s — "
                  f"{result.get('skip_reason')}: {result.get('detail', '')[:120]}")
            results.append({"date": d.isoformat(), "pkg": pkg, "cat": cat,
                            "action": "fetch_failed", "ok": False,
                            "error": result.get("detail")})
            continue

        # Integrity check
        v = verify_file(out)
        if v["ok"]:
            print(f"  [{pkg}/{cat:<11} {d}] OK in {elapsed:.1f}s  "
                  f"size={v['size_gz']:,}B  n_snapshots={v['n']}  "
                  f"ts=[{v['first_ts']}..{v['last_ts']}]  attempts={result.get('attempts', '?')}")
        else:
            print(f"  [{pkg}/{cat:<11} {d}] DOWNLOAD-OK BUT INTEGRITY-FAIL: {v['error']}")
        results.append({"date": d.isoformat(), "pkg": pkg, "cat": cat,
                        "action": "fetched", **v,
                        "fetch_elapsed_s": round(elapsed, 1),
                        "attempts": result.get("attempts")})

        time.sleep(bulk_pull.DELAY_BETWEEN_REQUESTS_S)

    # Summary
    print()
    print("=" * 70)
    print("REPULL SUMMARY")
    print("=" * 70)
    n_ok = sum(1 for r in results if r.get("ok"))
    n_fail = sum(1 for r in results if not r.get("ok"))
    print(f"  attempted: {len(results)}")
    print(f"  ok:        {n_ok}")
    print(f"  fail:      {n_fail}")
    print()
    for r in results:
        status = "OK " if r.get("ok") else "FAIL"
        action = r.get("action", "?")
        extra = ""
        if r.get("ok"):
            extra = f"  size={r.get('size_gz', 0):,}B  n={r.get('n')}"
        else:
            extra = f"  error={r.get('error') or '?'}"
        print(f"  [{status}] {r['date']}  {r['pkg']}/{r['cat']:<11} ({action}){extra}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

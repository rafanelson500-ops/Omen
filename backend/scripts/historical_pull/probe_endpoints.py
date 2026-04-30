"""Single-day probe of GexBot historical classic + state endpoints.

Mirrors the lib/gexbot.js production pipeline's two-step fetch:
  1. GET /v2/hist/{TICKER}/{pkg}/{cat}/{date}?noredirect with Bearer auth
       → returns {url: <presigned blob URL>}
  2. GET that presigned URL (no auth, may be gzipped) → actual JSON data

Saves the actual blob payload (decompressed if needed) to
backend/data/probes/{cat}_{date}.json so the user can inspect schema.

Read-only with respect to OMEN code; only writes to backend/data/probes/.
"""
from __future__ import annotations

import gzip
import io
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Endpoints from rafanelson500-ops/gexbot-pipeline:lib/gexbot.js (12 total).
# We exclude orderflow because OMEN already has that archive at backend/data/gex/.
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
PROBE_DATE = "2026-04-15"  # zero-padded, matches lib/gexbot.js convention
USER_AGENT = "GexbotPipeline/1.0-probe"

BACKEND = Path(__file__).resolve().parents[2]
PROBE_DIR = BACKEND / "data" / "probes"


def _shape_summary(payload):
    """Return a short string describing top-level shape + sample fields.
    Used to confirm the response looks like option-chain / state data and not an error page.
    """
    if isinstance(payload, list):
        n = len(payload)
        if n == 0:
            return "list[0] (empty)"
        first = payload[0]
        if isinstance(first, dict):
            keys = sorted(first.keys())
            sample_keys = ", ".join(keys[:8]) + ("…" if len(keys) > 8 else "")
            return f"list[{n}] of dict, first.keys=[{sample_keys}]"
        return f"list[{n}] of {type(first).__name__}"
    if isinstance(payload, dict):
        keys = sorted(payload.keys())
        sample_keys = ", ".join(keys[:8]) + ("…" if len(keys) > 8 else "")
        return f"dict[keys={sample_keys}]"
    return f"{type(payload).__name__}"


def _looks_like_error(payload) -> tuple[bool, str]:
    """Heuristic: detect if a JSON response is an error blob rather than data."""
    if isinstance(payload, dict):
        # Common error-shape keys
        for k in ("error", "errors", "message"):
            if k in payload and (
                "data" not in payload and "snapshots" not in payload
                and not isinstance(payload.get(k), list)
            ):
                return True, f"top-level dict has '{k}' key, no 'data'/'snapshots'"
        # Single-key dict with a string value is likely error or status message
        if len(payload) == 1 and isinstance(next(iter(payload.values())), str):
            return True, f"single string-valued dict: {payload}"
    return False, ""


def _maybe_gunzip(content: bytes) -> bytes:
    if content[:2] == b"\x1f\x8b":
        return gzip.decompress(content)
    return content


def probe_one(pkg: str, cat: str, date: str, api_key: str, sess: requests.Session) -> dict:
    presigned_url = f"{BASE_URL}/hist/{TICKER}/{pkg}/{cat}/{date}?noredirect"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    out = {
        "pkg": pkg, "cat": cat, "date": date,
        "presigned_url": presigned_url,
        "status_step1": None,
        "status_step2": None,
        "blob_bytes": 0,
        "decompressed_bytes": 0,
        "shape": None,
        "verdict": None,
        "detail": "",
        "saved_path": None,
    }
    # Step 1: presigned URL
    try:
        r1 = sess.get(presigned_url, headers=headers, timeout=15)
    except requests.RequestException as e:
        out["verdict"] = "FAIL"
        out["detail"] = f"step1 network error: {e!r}"
        return out
    out["status_step1"] = r1.status_code
    if r1.status_code != 200:
        out["verdict"] = "FAIL"
        out["detail"] = f"step1 HTTP {r1.status_code}: {r1.text[:200]}"
        return out
    try:
        meta = r1.json()
    except ValueError as e:
        out["verdict"] = "FAIL"
        out["detail"] = f"step1 non-JSON: {e!r} body[:200]={r1.text[:200]!r}"
        return out
    blob_url = meta.get("url") if isinstance(meta, dict) else None
    if not blob_url:
        out["verdict"] = "FAIL"
        out["detail"] = f"step1 missing 'url' field; payload={meta!r}"
        return out
    # Step 2: fetch the actual blob
    try:
        r2 = sess.get(blob_url, timeout=120)
    except requests.RequestException as e:
        out["verdict"] = "FAIL"
        out["detail"] = f"step2 network error: {e!r}"
        return out
    out["status_step2"] = r2.status_code
    if r2.status_code != 200:
        out["verdict"] = "FAIL"
        out["detail"] = f"step2 HTTP {r2.status_code}: {r2.text[:200]}"
        return out
    raw = r2.content
    out["blob_bytes"] = len(raw)
    decompressed = _maybe_gunzip(raw)
    out["decompressed_bytes"] = len(decompressed)
    if not decompressed:
        out["verdict"] = "FAIL"
        out["detail"] = "step2 empty body"
        return out
    try:
        payload = json.loads(decompressed.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        out["verdict"] = "FAIL"
        out["detail"] = f"step2 non-JSON: {e!r} head[:200]={decompressed[:200]!r}"
        return out
    shape = _shape_summary(payload)
    out["shape"] = shape
    err_flag, err_reason = _looks_like_error(payload)
    if err_flag:
        out["verdict"] = "FAIL"
        out["detail"] = f"response looks like an error: {err_reason}"
        return out
    # Save to disk
    save_path = PROBE_DIR / f"{cat}_{date}.json"
    save_path.write_bytes(decompressed)
    out["saved_path"] = str(save_path)
    # Verdict: SUCCESS unless shape is suspect (e.g. empty list)
    if isinstance(payload, list) and len(payload) == 0:
        out["verdict"] = "PARTIAL"
        out["detail"] = "empty list (endpoint reachable, no snapshots returned)"
    else:
        out["verdict"] = "SUCCESS"
        out["detail"] = shape
    return out


def main() -> None:
    load_dotenv(BACKEND / ".env")
    api_key = os.getenv("GEXBOT_API_KEY")
    if not api_key:
        print("ERROR: GEXBOT_API_KEY missing from .env", file=sys.stderr)
        sys.exit(2)

    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"PROBE: {len(ENDPOINTS)} endpoints, ticker={TICKER}, date={PROBE_DATE}")
    print(f"Saving to: {PROBE_DIR}")
    print()

    sess = requests.Session()
    results = []
    for pkg, cat in ENDPOINTS:
        t0 = time.time()
        r = probe_one(pkg, cat, PROBE_DATE, api_key, sess)
        elapsed = time.time() - t0
        results.append(r)
        verdict = r["verdict"] or "FAIL"
        print(f"  [{verdict:<7}] {pkg}/{cat:<11} "
              f"step1={r['status_step1']} step2={r['status_step2']} "
              f"raw={r['blob_bytes']:>10,}B uncompressed={r['decompressed_bytes']:>10,}B "
              f"({elapsed:.1f}s)")
        if r["shape"]:
            print(f"             shape: {r['shape']}")
        if r["verdict"] != "SUCCESS":
            print(f"             detail: {r['detail']}")
        # 1s pause between probes (be polite to the API)
        time.sleep(1.0)

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    by_verdict = {"SUCCESS": 0, "PARTIAL": 0, "FAIL": 0}
    for r in results:
        by_verdict[r["verdict"] or "FAIL"] += 1
    print(f"  SUCCESS: {by_verdict['SUCCESS']}")
    print(f"  PARTIAL: {by_verdict['PARTIAL']}")
    print(f"  FAIL:    {by_verdict['FAIL']}")
    print()
    if by_verdict["FAIL"] > 0:
        print("Failed endpoints:")
        for r in results:
            if r["verdict"] == "FAIL":
                print(f"  - {r['pkg']}/{r['cat']}: {r['detail']}")
        print()
    if by_verdict["PARTIAL"] > 0:
        print("Partial endpoints:")
        for r in results:
            if r["verdict"] == "PARTIAL":
                print(f"  - {r['pkg']}/{r['cat']}: {r['detail']}")
        print()

    # Write a structured summary too
    summary_path = PROBE_DIR / f"_probe_summary_{PROBE_DATE}.json"
    with summary_path.open("w") as f:
        # Drop presigned_url from the persisted summary (contains an
        # AWS-signed query string that's stable per-day; not a secret per se,
        # but unnecessary to commit).
        clean = [{k: v for k, v in r.items() if k != "presigned_url"} for r in results]
        json.dump({
            "probe_date": PROBE_DATE,
            "ticker": TICKER,
            "endpoints_attempted": len(ENDPOINTS),
            "by_verdict": by_verdict,
            "results": clean,
        }, f, indent=2)
    print(f"Structured summary written to: {summary_path}")


if __name__ == "__main__":
    main()

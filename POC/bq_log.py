"""
Privacy-safe BigQuery logging (Day 6.2). Writes interaction + guardrail metrics via
the key-free REST path (gcloud token + quota-project header), the same auth as
embed_index. NO original message is stored — only the DLP-scrubbed text and metrics;
the Telegram user id is hashed, never stored raw.

Three tables in dataset `ambassy`:
  interactions      — one row per answered / handed-off message
  guardrail_events  — one row per message (security signal, no message content)
  flow_events       — one row per LangGraph node per message (per-node trace):
                      request_id:STRING, ts:TIMESTAMP, user_hash:STRING, seq:INTEGER,
                      node:STRING, status:STRING, latency_ms:FLOAT, detail:STRING(JSON).
                      detail holds only metrics + public law refs, never the raw question.

Designed to NEVER break the bot: any failure (missing dataset, network, auth) is
caught, logged once, and then logging disables itself for the rest of the process.

    import bq_log; bq_log.log_interaction(user_id, out, latency_s)
"""
import hashlib
import json
import logging
import os
from datetime import datetime, timezone

import requests

from embed_index import get_token, PROJECT

log = logging.getLogger("ambassy.bqlog")

DATASET = os.environ.get("BQ_DATASET", "ambassy")
_BASE = "https://bigquery.googleapis.com/bigquery/v2"
_enabled = True   # flips to False after the first hard failure


def _user_hash(user_id):
    # POC: unkeyed sha256 so raw Telegram ids are never stored. Prod -> keyed/HMAC.
    return hashlib.sha256(f"ambassy:{user_id}".encode()).hexdigest()[:16]


def _insert(table, rows, token):
    """Insert one row (dict) or many (list of dicts) via streaming insertAll."""
    if isinstance(rows, dict):
        rows = [rows]
    if not rows:
        return
    url = f"{_BASE}/projects/{PROJECT}/datasets/{DATASET}/tables/{table}/insertAll"
    body = {"rows": [{"json": r} for r in rows]}
    headers = {"Authorization": f"Bearer {token}", "x-goog-user-project": PROJECT,
               "Content-Type": "application/json"}
    r = requests.post(url, json=body, headers=headers, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"insertAll {table} {r.status_code}: {r.text[:200]}")
    j = r.json()
    if j.get("insertErrors"):
        raise RuntimeError(f"insertAll {table} row errors: {j['insertErrors'][:1]}")


def _decision(out):
    g = out.get("guard", {})
    if g.get("action") and g["action"] != "allow":
        return g["action"]
    return out.get("router", {}).get("decision", "unknown")


def _top_paragraphs(out, n=5):
    parts = []
    for h in out.get("hits", [])[:n]:
        m = h.get("meta", {})
        label = f"{m.get('law_code', '')} {m.get('paragraph') or ''}".strip()
        parts.append(label or h.get("id", ""))
    return ", ".join(parts)


def log_interaction(user_id, out, latency_s):
    """One guardrail_events row (always) + one interactions row. Swallows all errors;
    disables itself after a hard failure so it can never take the bot down."""
    global _enabled
    if not _enabled:
        return
    try:
        token = get_token()
        uh = _user_hash(user_id)
        ts = datetime.now(timezone.utc).isoformat()
        g = out.get("guard", {})
        r = out.get("router", {})

        _insert("guardrail_events", {
            "ts": ts, "user_hash": uh,
            "action": g.get("action", "unknown"),
            "pii_found": bool(g.get("pii_found")),
            "pii_types": ", ".join(g.get("pii_types") or []),
            "on_topic": bool(g.get("on_topic")),
            "injection": bool(g.get("injection")),
        }, token)

        _insert("interactions", {
            "ts": ts, "user_hash": uh,
            "country": out.get("country", ""),
            "scrubbed_question": out.get("scrubbed", ""),   # PII-stripped, never the raw text
            "rewrite_de": out.get("rewritten", ""),
            "decision": _decision(out),
            "answerable": bool(r.get("answerable")) if r else None,
            "confidence": int(r["confidence"]) if r.get("confidence") is not None else None,
            "n_hits": len(out.get("hits", [])),
            "top_paragraphs": _top_paragraphs(out),
            "answer": out.get("answer", ""),
            "latency_s": round(float(latency_s), 2),
        }, token)

        # Per-node trace: one flow_events row per node (privacy-safe detail only).
        trace = out.get("trace") or []
        if trace:
            rid = out.get("request_id", "")
            _insert("flow_events", [{
                "request_id": rid, "ts": ts, "user_hash": uh, "seq": seq,
                "node": ev.get("node", ""), "status": ev.get("status", ""),
                "latency_ms": float(ev.get("latency_ms") or 0.0),
                "detail": json.dumps(ev.get("detail", {}), ensure_ascii=False),
            } for seq, ev in enumerate(trace)], token)
    except Exception as e:  # noqa: BLE001 — logging must never break the bot
        _enabled = False
        log.warning("BigQuery logging disabled after error: %s", e)

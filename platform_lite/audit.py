"""Append-only аудит у SQLite (у проді — ClickHouse/WORM, інтерфейс той самий)."""
import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT, request_id TEXT, tenant_id TEXT, user_id TEXT, role TEXT,
  method TEXT, path TEXT, status INTEGER,
  resource_type TEXT, resource_name TEXT,
  customer_ref TEXT, prompt_hash TEXT, decision TEXT,
  latency_ms INTEGER, cost_usd REAL, trace_json TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_tenant_ts ON audit_events(tenant_id, ts);
CREATE INDEX IF NOT EXISTS ix_audit_customer ON audit_events(tenant_id, customer_ref);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events
  BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events
  BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
"""

_lock = threading.Lock()


def _conn():
    c = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _lock, _conn() as c:
        c.executescript(SCHEMA)


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def customer_ref(tenant_id, customer_id):
    """Псевдонімізований ідентифікатор клієнта: у журналі немає «сирого» customer_id."""
    return sha256(f"{tenant_id}:{customer_id}")[:16]


def emit(**ev):
    ev.setdefault("ts", datetime.now(timezone.utc).isoformat())
    if "trace" in ev:
        ev["trace_json"] = json.dumps(ev.pop("trace"), ensure_ascii=False)
    cols = ["ts", "request_id", "tenant_id", "user_id", "role", "method", "path", "status",
            "resource_type", "resource_name", "customer_ref", "prompt_hash", "decision",
            "latency_ms", "cost_usd", "trace_json"]
    with _lock, _conn() as c:
        c.execute(f"INSERT INTO audit_events({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                  [ev.get(k) for k in cols])


def query(sql, params=()):
    with _lock, _conn() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def month_spend(tenant_id):
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    rows = query("SELECT COALESCE(SUM(cost_usd),0) AS s FROM audit_events "
                 "WHERE tenant_id=? AND substr(ts,1,7)=?", (tenant_id, month))
    return float(rows[0]["s"])

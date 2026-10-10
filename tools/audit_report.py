"""Заміна Grafana-дашборда: звіт із журналу аудиту (у проді ті самі запити виконує ClickHouse).
Запуск: python tools/audit_report.py [шлях_до_audit.db]"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def rows(db, sql, params=()):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    return [dict(r) for r in c.execute(sql, params).fetchall()]


def p95(values):
    v = sorted(values)
    return v[min(len(v) - 1, int(0.95 * len(v)))] if v else 0


def table(title, data, cols):
    print(f"\n── {title}")
    if not data:
        print("   (порожньо)")
        return
    w = {c: max(len(c), *(len(str(r[c])) for r in data)) for c in cols}
    print("   " + "  ".join(c.ljust(w[c]) for c in cols))
    for r in data:
        print("   " + "  ".join(str(r[c]).ljust(w[c]) for c in cols))


def main(db):
    per = []
    for t in rows(db, "SELECT DISTINCT tenant_id FROM audit_events ORDER BY 1"):
        ev = rows(db, "SELECT status, latency_ms, cost_usd FROM audit_events WHERE tenant_id=? AND method!='ALERT'",
                  (t["tenant_id"],))
        per.append({"tenant": t["tenant_id"], "requests": len(ev),
                    "2xx": sum(200 <= e["status"] < 300 for e in ev),
                    "401/403": sum(e["status"] in (401, 403) for e in ev),
                    "429": sum(e["status"] == 429 for e in ev),
                    "p95_ms": p95([e["latency_ms"] for e in ev]),
                    "cost_usd": round(sum(e["cost_usd"] or 0 for e in ev), 6)})
    table("Запити, помилки, затримка та витрати по орендарях", per,
          ["tenant", "requests", "2xx", "401/403", "429", "p95_ms", "cost_usd"])
    table("Відмови та політики (401/403/429)",
          rows(db, "SELECT tenant_id AS tenant, user_id AS user, path, status, decision FROM audit_events "
                   "WHERE status IN (401,403,429) ORDER BY id DESC LIMIT 12"),
          ["tenant", "user", "path", "status", "decision"])
    table("Алерти платформи",
          rows(db, "SELECT tenant_id AS tenant, decision FROM audit_events WHERE method='ALERT'"),
          ["tenant", "decision"])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / "audit.db")

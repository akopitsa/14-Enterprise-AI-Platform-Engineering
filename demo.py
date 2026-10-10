#!/usr/bin/env python3
"""Сценарна демонстрація Теми 14. Запуск:  python demo.py            (сам підніме шлюз)
                                           python demo.py --pause    (крок за кроком, Enter між сценаріями)
                                           python demo.py --url http://localhost:8000  (вже запущений шлюз; ті самі KEYS_DIR)"""
import argparse, json, os, subprocess, sys, tempfile, time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--url"); ap.add_argument("--pause", action="store_true")
ap.add_argument("--port", type=int, default=8099); ap.add_argument("--show-server-logs", action="store_true")
args = ap.parse_args()

ROOT = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="telco-demo-"))
if not args.url:                                     # ізольовані ключі та аудит для чистого прогону
    os.environ["KEYS_DIR"] = str(TMP / "keys"); os.environ["AUDIT_DB"] = str(TMP / "audit.db")
sys.path.insert(0, str(ROOT))
import httpx
from platform_lite import config, security

G, R, Y, B, D, X = "\033[32m", "\033[31m", "\033[33m", "\033[36m", "\033[2m", "\033[0m"
results, server = [], None


def banner(n, title, slide):
    print(f"\n{B}{'═' * 78}\n  Сценарій {n}: {title}   {D}(слайд {slide}){X}{B}\n{'═' * 78}{X}")
    if args.pause:
        input(f"{D}  [Enter] щоб виконати…{X}")


def tok(user, tenant, role, **kw):
    return security.issue_token(user, tenant, role, **kw)


def call(client, label, method, path, token=None, body=None, expect=200, headers=None, show=None, quiet=False):
    h = dict(headers or {})
    if token:
        h["Authorization"] = f"Bearer {token}"
    r = client.request(method, path, json=body, headers=h)
    ok = r.status_code == expect
    results.append((label, expect, r.status_code, ok))
    mark = f"{G}✅{X}" if ok else f"{R}❌ (очікувалось {expect}){X}"
    try:
        data = r.json()
    except Exception:
        data = {}
    brief = show(data) if (show and ok) else json.dumps(data, ensure_ascii=False)[:110]
    if not quiet:
        extra = f" retry-after={r.headers['retry-after']}s" if "retry-after" in r.headers else ""
        print(f"  {Y}{method:4}{X} {path:<42} → {r.status_code} {mark}{extra}\n       {D}{label}: {brief}{X}")
    return r, data


def wait_health(url):
    for _ in range(60):
        try:
            if httpx.get(url + "/health", timeout=1).status_code == 200:
                return
        except Exception:
            time.sleep(0.5)
    sys.exit("шлюз не стартував")


def pick(client, t, lo, hi):
    r = client.get("/v1/customers/at-risk?n=20", headers={"Authorization": "Bearer " + t})
    for c in r.json()["customers"]:
        if lo <= c["churn_probability"] < hi:
            return c["customer_id"]
    return r.json()["customers"][0]["customer_id"]


try:
    if args.url:
        url = args.url
    else:
        url = f"http://127.0.0.1:{args.port}"
        out = None if args.show_server_logs else subprocess.DEVNULL
        server = subprocess.Popen([sys.executable, "-m", "uvicorn", "platform_lite.gateway:app", "--port", str(args.port),
                                   "--log-level", "warning"], cwd=ROOT, env=os.environ.copy(), stdout=out, stderr=out)
    wait_health(url)
    c = httpx.Client(base_url=url, timeout=30)
    alice, bob, carol = (tok("alice@telco.com", "telco-crm", "viewer"), tok("bob@telco.com", "telco-crm", "operator"),
                         tok("carol@telco.com", "telco-crm", "admin"))
    print(f"{B}Шлюз: {url}   |   орендарі: {', '.join(config.TENANTS)}{X}")

    banner(1, "Автентифікація: без токена, підробка, прострочений токен", "42–43")
    call(c, "health публічний", "GET", "/health")
    call(c, "без токена", "GET", "/v1/models", expect=401)
    call(c, "підписаний ЧУЖИМ ключем", "GET", "/v1/models", tok("mallory", "telco-crm", "admin", rogue=True), expect=401)
    call(c, "прострочений", "GET", "/v1/models", tok("bob", "telco-crm", "operator", ttl_s=-60), expect=401)

    banner(2, "RBAC: viewer не може викликати модель, operator — може", "7, 13")
    cust = pick(c, bob, 0.0, 1.1)
    call(c, "viewer → predict", "POST", "/v1/models/churn-predictor/predict", alice, {"customer_id": cust}, expect=403)
    call(c, "operator → predict", "POST", "/v1/models/churn-predictor/predict", bob, {"customer_id": cust}, expect=200,
         show=lambda d: f"score={d['churn_probability']}, чинники: {[f['label'] for f in d['top_factors']]}")
    call(c, "operator → billing (admin-only)", "GET", "/v1/billing/usage", bob, expect=403)

    banner(3, "Ізоляція орендарів: чужий клієнт = 404, а підроблений X-Tenant-Id ігнорується", "7, 42")
    b2b_cust = "B1098"
    call(c, "crm-токен просить клієнта b2b", "POST", "/v1/models/churn-predictor/predict", bob, {"customer_id": b2b_cust}, expect=404)
    call(c, "X-Tenant-Id: telco-b2b у заголовку", "POST", "/v1/models/churn-predictor/predict", bob, {"customer_id": b2b_cust},
         expect=404, headers={"X-Tenant-Id": "telco-b2b"})
    call(c, "свій клієнт зі спуфінгом заголовка", "POST", "/v1/models/churn-predictor/predict", bob, {"customer_id": cust},
         expect=200, headers={"X-Tenant-Id": "telco-b2b"}, show=lambda d: "tenant береться з JWT → працює як crm")

    banner(4, "ГОЛОВНА ДЕМОНСТРАЦІЯ: запит менеджера → агент → наскрізний trace", "46–47")
    mid = pick(c, bob, 0.55, 0.75)
    r, d = call(c, f"агент для клієнта {mid}", "POST", "/v1/agents/retention-agent/invoke", bob, {"customer_id": mid,
         "question": "Чому цей клієнт йде?"}, expect=200, show=lambda d: f"status={d['status']}, offer={d['offer']['text']}")
    if r.status_code == 200:
        print(f"\n{D}  Пояснення:{X} {d['explanation']}\n{D}  {d['notice']}{X}\n{D}  Trace (як на слайді 47):{X}")
        print("  " + json.dumps({"request_id": d["request_id"], "tenant_id": d["tenant_id"], **d["trace"]},
                                ensure_ascii=False, indent=2).replace("\n", "\n  "))

    banner(5, "Guardrail у коді: знижка 25% > 15% → потрібне схвалення людини", "37–38, 30")
    top = pick(c, bob, 0.9, 1.1)
    r, d = call(c, f"агент для high-risk {top}", "POST", "/v1/agents/retention-agent/invoke", bob, {"customer_id": top},
                expect=200, show=lambda d: f"status={d['status']}, offer={d['offer']['text']}, approval={d.get('approval_id')}")
    aid = d.get("approval_id")
    call(c, "operator намагається схвалити сам", "POST", f"/v1/approvals/{aid}/decide", bob, {"approve": True}, expect=403)
    call(c, "admin бачить чергу схвалень", "GET", "/v1/approvals", carol, expect=200, show=lambda d: f"{len(d['pending'])} в очікуванні")
    call(c, "admin схвалює", "POST", f"/v1/approvals/{aid}/decide", carol, {"approve": True}, expect=200,
         show=lambda d: f"{d['status']} by {d['decided_by']}")

    banner(6, "Rate limit (token bucket) для telco-b2b: 6 запитів/хв", "15, 44")
    dave = tok("dave@b2b.com", "telco-b2b", "operator")
    codes = [call(c, f"запит #{i}", "GET", "/v1/models", dave, expect=200 if i <= 6 else 429, quiet=True)[0].status_code
             for i in range(1, 10)]
    print(f"  Статуси 9 запитів поспіль: {' '.join((G if s == 200 else R) + str(s) + X for s in codes)}")
    print(f"  {D}інші орендарі не страждають — ліміт на орендаря:{X}")
    call(c, "crm у цей же момент", "GET", "/v1/models", bob, expect=200, show=lambda d: "ok")

    banner(7, "Облік витрат: бюджет telco-trial $0.0012 → alert на 90% → блок на 4-му запиті", "17, 44")
    erin = tok("erin@trial.com", "telco-trial", "operator")
    tcust = pick(c, erin, 0.0, 1.1)
    for i in range(1, 6):
        r, d = call(c, f"агент #{i}", "POST", "/v1/agents/retention-agent/invoke", erin, {"customer_id": tcust},
                    expect=200 if i <= 3 else 429, show=lambda d: (f"cost=${d['trace']['total_cost_usd']}" + ("  ⚠️ budget_alert" if d.get("budget_alert") else "")
                                    if "trace" in d else f"БЛОК: {d['error']} — витрачено ${d['spent_usd']} з ${d['budget_usd']}"))
        if r.status_code == 429:
            break

    banner(8, "Комплаєнс: usage, «усі рішення щодо клієнта X», незмінність журналу", "26, 28–29")
    call(c, "admin: billing usage", "GET", "/v1/billing/usage", carol, expect=200,
         show=lambda d: f"spent=${d['spent_usd']} з ${d['budget_usd']} ({d['budget_used_pct']}%)")
    r, d = call(c, f"admin: аудит щодо {top}", "GET", f"/v1/audit/customers/{top}", carol, expect=200,
                show=lambda d: f"подій у журналі: {len(d['events'])}")
    for e in d.get("events", []):
        print(f"       {D}{e['ts'][11:19]} {e['path']:<34} {e['status']} {e['decision']}{X}")
    call(c, "operator: аудит (admin-only)", "GET", f"/v1/audit/customers/{top}", bob, expect=403)
    if not args.url:
        import sqlite3
        db = sqlite3.connect(os.environ["AUDIT_DB"])
        try:
            db.execute("DELETE FROM audit_events"); blocked = False
        except sqlite3.DatabaseError as e:
            blocked = True; msg = str(e)
        results.append(("DELETE з audit_events заблоковано", "blocked", "blocked" if blocked else "DELETED", blocked))
        print(f"  {G if blocked else R}{'✅' if blocked else '❌'}{X} спроба DELETE FROM audit_events → {msg if blocked else 'ВИДАЛЕНО!'}")
        print(f"\n{B}Звіт з аудиту (заміна дашборда Grafana):{X}")
        sys.path.insert(0, str(ROOT / "tools")); import audit_report; audit_report.main(os.environ["AUDIT_DB"])

    bad = [r for r in results if not r[3]]
    print(f"\n{B}{'═' * 78}{X}\n  Перевірок: {len(results)}   {G}успішно: {len(results) - len(bad)}{X}   "
          f"{R if bad else G}невдало: {len(bad)}{X}")
    for label, exp, got, _ in bad:
        print(f"   {R}❌ {label}: очікувалось {exp}, отримано {got}{X}")
    sys.exit(1 if bad else 0)
finally:
    if server:
        server.terminate()

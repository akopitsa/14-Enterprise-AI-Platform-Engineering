"""Багатоорендний AI-шлюз. Життєвий цикл запиту (слайд 15):
authn (middleware) -> authz + rate limit (залежність маршруту) -> маршрутизація -> облік і аудит (middleware)."""
import time
import uuid
from contextlib import asynccontextmanager

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import audit, config, cost, security
from .ratelimit import TokenBucket
from .tiers import agent, ml

limiter = TokenBucket()
STATE = {}


@asynccontextmanager
async def lifespan(app):
    security.ensure_keys()
    audit.init()
    STATE["model"], STATE["card"] = ml.load()        # CI-gate: без картки/AUC — не стартуємо
    yield


app = FastAPI(title="AI Platform Gateway (lite)", lifespan=lifespan)


def guarded(scope):
    """authz (403) + rate limit (429) — після authn, перед виконанням маршруту."""
    base = security.require_scope(scope)

    def _dep(request: Request):
        claims = base(request)
        t = claims["tenant_id"]
        ok, retry = limiter.allow(t, config.TENANTS[t]["rate_per_min"])
        if not ok:
            request.state.decision = "rate_limited"
            raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": str(int(retry) + 1)})
        return claims
    return _dep


@app.middleware("http")
async def lifecycle(request: Request, call_next):
    t0 = time.perf_counter()
    rid = request.headers.get("x-request-id") or "req_" + uuid.uuid4().hex[:8]
    st = request.state
    st.request_id, st.claims = rid, None
    st.decision = st.resource_type = st.resource_name = st.customer_ref = st.prompt_hash = st.trace = None
    st.cost_usd = 0.0
    try:
        if request.url.path in config.PUBLIC_PATHS:
            resp = await call_next(request)
        else:
            token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
            try:
                claims = security.verify_token(token)
                if claims.get("tenant_id") not in config.TENANTS:
                    raise jwt.InvalidTokenError("unknown tenant")
                st.claims = claims            # tenant_id беремо ЛИШЕ з підписаного JWT, не із заголовків
                resp = await call_next(request)
            except jwt.PyJWTError as e:
                st.decision = f"401: {type(e).__name__}"
                resp = JSONResponse({"error": "unauthorized"}, status_code=401)
    except Exception as e:                    # noqa
        st.decision = f"500: {type(e).__name__}"
        resp = JSONResponse({"error": "internal"}, status_code=500)
    resp.headers["x-request-id"] = rid
    c = st.claims or {}
    audit.emit(request_id=rid, tenant_id=c.get("tenant_id", "unknown"), user_id=c.get("sub", "anonymous"),
               role=c.get("role"), method=request.method, path=request.url.path, status=resp.status_code,
               resource_type=st.resource_type, resource_name=st.resource_name, customer_ref=st.customer_ref,
               prompt_hash=st.prompt_hash, decision=st.decision,
               latency_ms=int((time.perf_counter() - t0) * 1000), cost_usd=st.cost_usd, trace=st.trace)
    return resp


class CustomerIn(BaseModel):
    customer_id: str
    question: str | None = None


class DecisionIn(BaseModel):
    approve: bool


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/v1/models")
def list_models(request: Request, claims=Depends(guarded("models:read"))):
    card = STATE["card"]["model_card"]
    return {"models": [
        {"name": "churn-predictor", "stage": card["registry_stage"], "auc": card["evaluation"]["auc"]},
        {"name": "explainer-llm", "backend": config.LLM_BACKEND}]}


@app.get("/v1/models/churn-predictor/card")
def model_card(claims=Depends(guarded("models:read"))):
    return STATE["card"]


@app.get("/v1/customers/at-risk")
def at_risk(n: int = 5, claims=Depends(guarded("models:read"))):
    return {"tenant_id": claims["tenant_id"], "customers": STATE["model"].at_risk(claims["tenant_id"], min(n, 20))}


@app.post("/v1/models/{model}/predict")
def predict(model: str, body: CustomerIn, request: Request, claims=Depends(guarded("models:invoke"))):
    if model != "churn-predictor":
        raise HTTPException(404, "not found")
    t = claims["tenant_id"]
    request.state.resource_type, request.state.resource_name = "model", model
    request.state.customer_ref = audit.customer_ref(t, body.customer_id)
    pred = STATE["model"].predict(t, body.customer_id)
    if pred is None:
        request.state.decision = "not_found_or_foreign"
        raise HTTPException(404, "not found")          # не розкриваємо, чи існує клієнт в іншого орендаря
    request.state.decision = f"score={pred['churn_probability']}"
    return pred


@app.post("/v1/agents/{agent_id}/invoke")
def invoke_agent(agent_id: str, body: CustomerIn, request: Request, claims=Depends(guarded("agents:invoke"))):
    if agent_id != "retention-agent":
        raise HTTPException(404, "not found")
    t = claims["tenant_id"]
    st = request.state
    st.resource_type, st.resource_name = "agent", agent_id
    st.customer_ref = audit.customer_ref(t, body.customer_id)

    before = cost.budget_state(t)
    if before["exhausted"]:
        st.decision = "budget_exceeded"
        return JSONResponse({"error": "budget_exceeded", "budget_usd": before["budget"],
                             "spent_usd": round(before["spent"], 6)}, status_code=429)

    trace = agent.Trace()
    try:
        out = agent.run(STATE["model"], t, claims["sub"], body.customer_id, trace)
    except agent.GuardrailViolation as e:
        st.decision = f"blocked: {e}"
        return JSONResponse({"error": "guardrail_violation", "detail": str(e)}, status_code=422)
    if out is None:
        st.decision = "not_found_or_foreign"
        raise HTTPException(404, "not found")

    c = out.pop("llm_cost_usd")
    st.prompt_hash = audit.sha256(out.pop("prompt"))     # сирий промпт у журнал не потрапляє
    st.cost_usd = c
    st.decision = out["status"] + (" (low_confidence)" if out["low_confidence"] else "")
    budget = config.TENANTS[t]["monthly_budget_usd"]
    if before["spent"] + c > 0.9 * budget >= before["spent"]:      # перетин порога 90% — один раз
        audit.emit(request_id=st.request_id, tenant_id=t, user_id="platform", role="system", method="ALERT",
                   path="/_alert/budget", status=299, resource_type="platform", resource_name="budget",
                   decision=f"budget_alert: {round(100 * (before['spent'] + c) / budget)}% of ${budget}",
                   latency_ms=0, cost_usd=0.0)
        out["budget_alert"] = True
    summary = {"steps": trace.steps, "total_latency_ms": trace.total_ms(), "total_cost_usd": round(c, 6)}
    st.trace = {"request_id": st.request_id, **summary}
    return {"request_id": st.request_id, "tenant_id": t, **out, "trace": summary}


@app.get("/v1/approvals")
def pending(claims=Depends(guarded("approvals:decide"))):
    return {"pending": [{"id": k, **v} for k, v in agent.APPROVALS.items()
                        if v["tenant_id"] == claims["tenant_id"] and v["status"] == "pending"]}


@app.post("/v1/approvals/{approval_id}/decide")
def decide(approval_id: str, body: DecisionIn, request: Request, claims=Depends(guarded("approvals:decide"))):
    a = agent.decide(approval_id, claims["tenant_id"], body.approve, claims["sub"])
    if a is None:
        raise HTTPException(404, "not found")
    request.state.resource_type, request.state.resource_name = "approval", approval_id
    request.state.customer_ref = audit.customer_ref(claims["tenant_id"], a["customer_id"])
    request.state.decision = a["status"]
    return {"approval_id": approval_id, "status": a["status"], "decided_by": claims["sub"]}


@app.get("/v1/billing/usage")
def usage(claims=Depends(guarded("billing:read"))):
    t = claims["tenant_id"]
    rows = audit.query("SELECT substr(ts,1,10) AS day, resource_name AS resource, COUNT(*) AS calls, "
                       "ROUND(SUM(cost_usd),6) AS cost_usd FROM audit_events "
                       "WHERE tenant_id=? AND resource_type IS NOT NULL GROUP BY day, resource ORDER BY day", (t,))
    b = cost.budget_state(t)
    return {"tenant_id": t, "budget_usd": b["budget"], "spent_usd": round(b["spent"], 6),
            "budget_used_pct": b["pct"], "by_day": rows}


@app.get("/v1/audit/customers/{customer_id}")
def audit_for_customer(customer_id: str, claims=Depends(guarded("audit:read"))):
    """Запит комплаєнсу (GDPR, слайди 26/29): усі рішення щодо клієнта X — лише в межах свого орендаря."""
    t = claims["tenant_id"]
    rows = audit.query("SELECT ts, request_id, path, status, resource_name, decision, cost_usd FROM audit_events "
                       "WHERE tenant_id=? AND customer_ref=? ORDER BY id", (t, audit.customer_ref(t, customer_id)))
    return {"customer_id": customer_id, "events": rows}

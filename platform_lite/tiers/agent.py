"""Рівень агента: скінченний автомат (ті самі вузли, що на слайді 38) + guardrails у коді + human-in-the-loop.
Без залежності від LangGraph, щоб демо не ламалось через версії; вузли 1:1 переносяться в StateGraph."""
import time
import uuid

from .. import config, cost
from . import llm, rag


class GuardrailViolation(Exception):
    pass


PROHIBITED = ["гарантуємо безкоштовно", "безкоштовно назавжди", "без жодних умов"]
APPROVALS = {}   # approval_id -> dict (у проді — БД/черга)


class Trace:
    def __init__(self):
        self.steps, self.t0 = [], time.perf_counter()

    def run(self, tier, op, fn, summarize=None):
        t = time.perf_counter()
        result = fn()
        step = {"tier": tier, "op": op, "latency_ms": round((time.perf_counter() - t) * 1000, 1)}
        if summarize:
            step.update(summarize(result))
        self.steps.append(step)
        return result

    def total_ms(self):
        return round((time.perf_counter() - self.t0) * 1000, 1)


class ToolRegistry:
    """Локальна заміна MCP-сервера: той самий інтерфейс call_tool(name, **args)."""
    def call_tool(self, name, **args):
        if name == "offer_catalog.suggest":
            s = args["churn_score"]
            pct = 0 if s < 0.35 else 5 if s < 0.55 else 12 if s < 0.75 else 25
            text = (f"{pct}% знижка лояльності + пріоритетна підтримка" if pct else "Без пропозиції — моніторинг")
            return {"discount_pct": pct, "text": text}
        raise KeyError(name)


MCP = ToolRegistry()


def guardrail_check(offer):
    """Виконується в коді: модель не може це обійти (слайд 38)."""
    if any(p in offer["text"].lower() for p in PROHIBITED):
        raise GuardrailViolation("prohibited language in offer")
    return offer["discount_pct"] > config.MAX_AUTO_DISCOUNT


def run(model, tenant_id, user, customer_id, trace):
    pred = trace.run("ml", "predict", lambda: model.predict(tenant_id, customer_id),
                     lambda r: {"result": f"score={r['churn_probability']}"} if r else {"result": "not_found"})
    if pred is None:
        return None
    feats = [f["feature"] for f in pred["top_factors"]]
    query = "retention offers for churn factors: " + ", ".join(feats)
    docs = trace.run("llm", "retrieve", lambda: rag.search(tenant_id, query, feats, top_k=3),
                     lambda r: {"result": f"{len(r)} docs"})
    ex = trace.run("llm", "explain", lambda: llm.explain(pred["churn_probability"], pred["top_factors"], docs),
                   lambda r: {"backend": r["backend"]})
    ctx = " ".join(d["text"] + " " + d["title"] for d in docs) + " " + " ".join(f["label"] for f in pred["top_factors"])
    faith = llm.faithfulness_proxy(ex["text"], ctx)
    trace.steps[-1]["faithfulness_proxy"] = faith
    low_conf = faith < config.FAITHFULNESS_MIN

    llm_cost = cost.llm_cost("explainer-llm", ex["in_tokens"], ex["out_tokens"])
    offer = trace.run("agent", "draft_offer", lambda: MCP.call_tool("offer_catalog.suggest", churn_score=pred["churn_probability"]),
                      lambda r: {"discount_pct": r["discount_pct"]})
    needs_approval = trace.run("agent", "guardrail_check", lambda: guardrail_check(offer),
                               lambda r: {"needs_approval": r, "limit_pct": config.MAX_AUTO_DISCOUNT})

    out = {"customer_id": customer_id, "churn_score": pred["churn_probability"], "top_factors": pred["top_factors"],
           "explanation": ex["text"], "low_confidence": low_conf, "offer": offer,
           "notice": "Ви спілкуєтеся з AI-асистентом", "llm_cost_usd": llm_cost, "prompt": ex["prompt"]}
    if needs_approval:
        aid = "apr_" + uuid.uuid4().hex[:6]
        APPROVALS[aid] = {"tenant_id": tenant_id, "customer_id": customer_id, "offer": offer,
                          "requested_by": user, "status": "pending"}
        trace.steps.append({"tier": "agent", "op": "human_approval", "result": "pending", "approval_id": aid})
        out.update(status="pending_approval", approval_id=aid)
    else:
        trace.steps.append({"tier": "agent", "op": "send_offer", "result": "sent"})
        out.update(status="offer_sent")
    return out


def decide(approval_id, tenant_id, approve, by):
    a = APPROVALS.get(approval_id)
    if not a or a["tenant_id"] != tenant_id:       # чужі approval-и «не існують»
        return None
    if a["status"] != "pending":
        return a
    a["status"] = "approved_and_sent" if approve else "rejected"
    a["decided_by"] = by
    return a

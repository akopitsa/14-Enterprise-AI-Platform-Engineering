"""Облік витрат за фактичними токенами + перевірка бюджету (bюджет береться з аудиту)."""
from . import audit, config


def llm_cost(model, in_tokens, out_tokens):
    rin, rout = config.TOKEN_RATES[model]
    return in_tokens / 1000 * rin + out_tokens / 1000 * rout


def budget_state(tenant_id):
    budget = config.TENANTS[tenant_id]["monthly_budget_usd"]
    spent = audit.month_spend(tenant_id)
    return {"budget": budget, "spent": spent, "exhausted": spent >= budget,
            "pct": round(100 * spent / budget, 1) if budget else 0.0}

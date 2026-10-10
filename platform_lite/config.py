import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYS_DIR = Path(os.getenv("KEYS_DIR", ROOT / ".keys"))
DB_PATH = Path(os.getenv("AUDIT_DB", ROOT / "audit.db"))
ARTIFACTS_DIR = ROOT / "artifacts"
POLICY_FILE = ROOT / "policies" / "rbac.yaml"

JWT_ISSUER = "idp.telco.local"
JWT_AUDIENCE = "ai-platform"

MAX_AUTO_DISCOUNT = 15          # % — вище потрібне схвалення людини (guardrail)
PROMOTION_MIN_AUC = 0.75        # поріг просування моделі (CI gate)
FAITHFULNESS_MIN = 0.7          # нижче — позначаємо відповідь для перевірки

# Орендарі: ліміт запитів/хв (token bucket) та місячний бюджет (costCeiling зі слайду 17)
TENANTS = {
    "telco-crm":   {"rate_per_min": 60, "monthly_budget_usd": 50.0},
    "telco-b2b":   {"rate_per_min": 6,  "monthly_budget_usd": 50.0},    # малий ліміт -> демо 429
    "telco-trial": {"rate_per_min": 60, "monthly_budget_usd": 0.0012},   # малий бюджет: ~3 запити до alert (90%), 4-й блокується
}

# USD за 1K токенів (вхід, вихід) — навмисно «круглі» числа для наочної демонстрації
TOKEN_RATES = {"explainer-llm": (0.002, 0.006)}

PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

# Опційно: реальна LLM через OpenAI-сумісний API (OpenRouter / Ollama / vLLM)
LLM_BACKEND = os.getenv("LLM_BACKEND", "stub")        # stub | openai
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "openrouter/free")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")

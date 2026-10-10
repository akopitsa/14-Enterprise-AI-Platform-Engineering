# telco-platform-lite — легка демонстрація Теми 14

Мінімальна, але **справжня** реалізація *рівня платформи* з Теми 14: JWT-шлюз, RBAC із політики в Git,
ізоляція орендарів, token-bucket, облік витрат і бюджети, append-only аудит, наскрізний `request_id`-trace,
guardrails у коді з людським схваленням, CI-gate картки моделі та IDP-валідатор маніфестів.
Важкі компоненти (vLLM, векторна БД, K8s, ClickHouse) замінені заглушками з тими самими контрактами.

## Запуск (≈1 хвилина, без GPU, Docker і ключів)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python demo.py                 # усі 8 сценаріїв + самоперевірка (код виходу 0, якщо все ок)
python demo.py --pause         # покроково для заняття: Enter між сценаріями
python tools/idp_validate.py idp_requests/good-retention-agent.yaml   # ✅
python tools/idp_validate.py idp_requests/bad-shadow-llm.yaml         # ❌ 7 порушень
```

Окремий шлюз (щоб показати логи сервера поруч): 
```bash
uvicorn platform_lite.gateway:app --port 8000          # термінал 1
python demo.py --url http://127.0.0.1:8000             # термінал 2 (ті самі .keys/ і audit.db)
```
Ручні запити (токен видає «IdP» у `security.py`):
```bash
TOKEN=$(python -c "from platform_lite import security as s; print(s.issue_token('bob','telco-crm','operator'))")
curl -s localhost:8000/v1/customers/at-risk -H "Authorization: Bearer $TOKEN"
```

## Структура
| Файл | Тема / слайди |
|---|---|
| `platform_lite/gateway.py` | Життєвий цикл запиту: authn → authz → rate limit → маршрутизація → облік/аудит (сл. 12–15, 42–45) |
| `platform_lite/security.py`, `policies/rbac.yaml` | JWT RS256, RBAC як код (сл. 7, 13) |
| `platform_lite/ratelimit.py` | Справжній token bucket (сл. 15, 44) |
| `platform_lite/audit.py` | Append-only аудит, хеш промпту, псевдонімізація клієнта (сл. 26–27, 45) |
| `platform_lite/cost.py`, `config.py` | Токени → USD, бюджети орендарів (сл. 17, 44) |
| `platform_lite/tiers/ml.py` | Рівень ML + картка моделі + CI-gate (сл. 24–25, 33–34) |
| `platform_lite/tiers/rag.py`, `llm.py` | Рівень LLM: RAG на орендаря, пояснення (сл. 35–36) |
| `platform_lite/tiers/agent.py` | Рівень агента: вузли, guardrail, human approval, trace (сл. 37–38, 46–47) |
| `tools/idp_validate.py`, `policies/idp.yaml`, `idp_requests/` | IDP-запобіжники (сл. 16–17) |
| `tools/audit_report.py` | Заміна Grafana-дашборда |

## Реальна LLM (опційно)
Будь-який OpenAI-сумісний бекенд (OpenRouter, Ollama, vLLM):
```bash
LLM_BACKEND=openai LLM_BASE_URL=https://openrouter.ai/api/v1 LLM_MODEL=openrouter/free LLM_API_KEY=... python demo.py
# Ollama:  LLM_BASE_URL=http://localhost:11434/v1  LLM_MODEL=mistral:7b-instruct-q4_K_M
```
При будь-якій помилці бекенду шлюз мовчки повертається до заглушки — демо не зламається посеред заняття.

## Обмеження (чесно)
Ліміти, схвалення та токени — у пам'яті одного процесу; SQLite-тригери ілюструють append-only, але не захищають від адміністратора БД
(у проді — ClickHouse з обмеженими грантами / WORM); `faithfulness_proxy` — лексичний проксі, а не RAGAS; дані синтетичні.

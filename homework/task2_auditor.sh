#!/usr/bin/env bash
# Завдання 2: роль auditor (лише audit:read) — три перевірки через curl.
# Запуск із кореня репозиторію:  bash homework/task2_auditor.sh | tee homework/task2_output.txt
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
PORT=${PORT:-8011}
URL="http://127.0.0.1:$PORT"

# Ізольовані ключі та журнал аудиту, щоб прогін був відтворюваним
WORK=$(mktemp -d); export KEYS_DIR="$WORK/keys" AUDIT_DB="$WORK/audit.db"
"$PY" -m uvicorn platform_lite.gateway:app --port "$PORT" --log-level warning &
SERVER=$!; trap 'kill $SERVER 2>/dev/null; rm -rf "$WORK"' EXIT
until curl -sf "$URL/health" >/dev/null; do sleep 0.3; done

echo "\$ grep -A1 'auditor:' policies/rbac.yaml"
grep -A1 'auditor:' policies/rbac.yaml
echo

AUDITOR=$("$PY" -c 'from platform_lite import security; print(security.issue_token("ivan@telco.com", "telco-crm", "auditor"))')
OPERATOR=$("$PY" -c 'from platform_lite import security; print(security.issue_token("bob@telco.com", "telco-crm", "operator"))')

# Підготовка: operator робить прогноз для реального клієнта, щоб у журналі аудиту були події
CUST=$(curl -s "$URL/v1/customers/at-risk?n=1" -H "Authorization: Bearer $OPERATOR" \
       | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["customers"][0]["customer_id"])')
curl -s -o /dev/null -X POST "$URL/v1/models/churn-predictor/predict" -H "Authorization: Bearer $OPERATOR" \
     -H 'Content-Type: application/json' -d "{\"customer_id\": \"$CUST\"}"
echo "Токен ivan@telco.com / telco-crm / auditor видано; клієнт для перевірки: $CUST"
echo

req() {   # req <очікуваний код> <опис> <curl-аргументи...>
  local expect=$1 label=$2; shift 2
  local body code
  body=$(curl -s -w $'\n%{http_code}' -H "Authorization: Bearer $AUDITOR" "$@")
  code=${body##*$'\n'}; body=${body%$'\n'*}
  local mark="OK"; [[ $code == "$expect" ]] || mark="FAIL (очікувалось $expect)"
  echo "── $label"
  echo "   curl $*"
  echo "   HTTP $code  [$mark]"
  echo "   $body"
  echo
}

req 200 "1) auditor → GET /v1/audit/customers/$CUST" "$URL/v1/audit/customers/$CUST"
req 403 "2) auditor → POST /v1/models/churn-predictor/predict" -X POST "$URL/v1/models/churn-predictor/predict" \
    -H 'Content-Type: application/json' -d "{\"customer_id\": \"$CUST\"}"
req 403 "3) auditor → GET /v1/billing/usage" "$URL/v1/billing/usage"

echo "── Журнал аудиту фіксує і відмови auditor-а (decision з шлюзу):"
"$PY" - <<'EOF'
import os, sqlite3
db = sqlite3.connect(os.environ["AUDIT_DB"])
for row in db.execute("SELECT user_id, role, method, path, status, decision FROM audit_events "
                      "WHERE role='auditor' ORDER BY id"):
    print("  ", " | ".join(str(x) for x in row))
EOF

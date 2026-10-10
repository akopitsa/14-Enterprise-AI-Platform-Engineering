"""Рівень ML. Синтетичні дані + LogisticRegression (секунди замість хвилин).
Для лінійної моделі точні внески ознак = coef * z-score (аналог SHAP). На слайді — GradientBoosting+SHAP:
міняється лише цей файл, контракт predict() лишається тим самим."""
import yaml
import numpy as np
from datetime import datetime, timezone
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from .. import config

FEATURES = ["tenure_months", "monthly_charge", "support_calls_30d",
            "data_usage_change_pct", "contract_months", "late_payments_90d"]
HUMAN = {
    "tenure_months": "мала тривалість обслуговування",
    "monthly_charge": "високий щомісячний рахунок",
    "support_calls_30d": "багато звернень до підтримки",
    "data_usage_change_pct": "падіння використання даних",
    "contract_months": "короткий/місячний контракт",
    "late_payments_90d": "прострочені платежі",
}
PREFIX = {"telco-crm": ("C", 400), "telco-b2b": ("B", 150), "telco-trial": ("T", 60)}


class ChurnModel:
    def __init__(self):
        rng = np.random.default_rng(7)
        rows, ids, tenants = [], [], []
        for tenant, (p, n) in PREFIX.items():
            for i in range(n):
                tenure = float(rng.integers(1, 72))
                charge = float(np.clip(rng.normal(55, 18), 15, 130))
                calls = float(rng.poisson(1.2))
                usage = float(rng.normal(0, 25))
                contract = float(rng.choice([1, 12, 24], p=[.5, .3, .2]))
                late = float(rng.poisson(0.4))
                rows.append([tenure, charge, calls, usage, contract, late])
                ids.append(f"{p}{1001 + i}")
                tenants.append(tenant)
        X = np.array(rows)
        logit = 1.8 * (-0.9 - 0.035 * X[:, 0] + 0.025 * (X[:, 1] - 55) + 0.55 * X[:, 2]
                       - 0.015 * X[:, 3] - 0.03 * X[:, 4] + 0.7 * X[:, 5])
        y = (rng.random(len(X)) < 1 / (1 + np.exp(-logit))).astype(int)
        self.X, self.ids, self.tenants = X, ids, np.array(tenants)
        self.scaler = StandardScaler().fit(X)
        Xtr, Xte, ytr, yte = train_test_split(self.scaler.transform(X), y, test_size=0.3,
                                              random_state=1, stratify=y)
        self.clf = LogisticRegression(max_iter=500).fit(Xtr, ytr)
        self.auc = float(roc_auc_score(yte, self.clf.predict_proba(Xte)[:, 1]))
        self.train_rows = int(len(Xtr))
        self.index = {cid: i for i, cid in enumerate(ids)}
        Z = self.scaler.transform(X)
        self.scores = self.clf.predict_proba(Z)[:, 1]
        self.contrib = Z * self.clf.coef_[0]

    def owns(self, tenant_id, customer_id):
        i = self.index.get(customer_id)
        return i is not None and self.tenants[i] == tenant_id

    def predict(self, tenant_id, customer_id):
        """None, якщо клієнта не існує або він належить іншому орендарю (не розкриваємо різницю)."""
        if not self.owns(tenant_id, customer_id):
            return None
        i = self.index[customer_id]
        top = np.argsort(-self.contrib[i])[:3]
        factors = [{"feature": FEATURES[j], "label": HUMAN[FEATURES[j]],
                    "value": round(float(self.X[i, j]), 1),
                    "contribution": round(float(self.contrib[i, j]), 3)}
                   for j in top if self.contrib[i, j] > 0]
        return {"customer_id": customer_id, "churn_probability": round(float(self.scores[i]), 3),
                "top_factors": factors}

    def at_risk(self, tenant_id, n=5):
        idx = [i for i in np.argsort(-self.scores) if self.tenants[i] == tenant_id][:n]
        return [{"customer_id": self.ids[i], "churn_probability": round(float(self.scores[i]), 3)}
                for i in idx]

    def model_card(self):
        return {"model_card": {
            "name": "churn-predictor", "version": "1.0.0", "registry_stage": "Production",
            "owner_team": "telco-ml-platform",
            "intended_use": {"description": "Ймовірність відтоку клієнта за 30 днів для пріоритезації утримання.",
                             "out_of_scope": ["credit risk scoring", "individual pricing"]},
            "training_data": {"source": "synthetic_demo", "rows": self.train_rows,
                              "pii_fields_removed": ["msisdn", "full_name", "address"]},
            "evaluation": {"auc": round(self.auc, 3)},
            "limitations": ["Демо на синтетичних даних", "Не оцінювалась справедливість за сегментами"],
            "generated_by": "eval-pipeline (demo)",
            "generated_at": datetime.now(timezone.utc).isoformat()}}


def promotion_gate(card):
    """CI-gate зі слайду 24: без повної картки і AUC вище порогу — модель не просувається."""
    mc = card.get("model_card", {})
    for field in ("intended_use", "training_data", "evaluation", "limitations", "owner_team"):
        if not mc.get(field):
            raise RuntimeError(f"promotion blocked: model card missing '{field}'")
    if mc["evaluation"]["auc"] < config.PROMOTION_MIN_AUC:
        raise RuntimeError(f"promotion blocked: AUC {mc['evaluation']['auc']} < {config.PROMOTION_MIN_AUC}")
    return True


def load():
    m = ChurnModel()
    card = m.model_card()
    promotion_gate(card)
    config.ARTIFACTS_DIR.mkdir(exist_ok=True)
    (config.ARTIFACTS_DIR / "model_card.yaml").write_text(
        yaml.safe_dump(card, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return m, card

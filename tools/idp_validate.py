"""Крок CI у IDP: валідує маніфест самообслуговування проти policies/idp.yaml.
Запуск: python tools/idp_validate.py idp_requests/good-retention-agent.yaml"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def validate(manifest, policy):
    v, s = [], manifest.get("spec", {})
    if s.get("baseImage") not in policy["approved_base_images"]:
        v.append(f"baseImage '{s.get('baseImage')}' не з переліку схвалених образів")
    gpu = s.get("resources", {}).get("gpu", 0)
    if gpu > policy["max_gpu_per_deployment"]:
        v.append(f"gpu={gpu} перевищує ліміт {policy['max_gpu_per_deployment']}")
    rep = s.get("resources", {}).get("replicas", {})
    if rep.get("min", 0) < 1 or rep.get("max", 0) < rep.get("min", 0):
        v.append(f"replicas некоректні: {rep}")
    cc = s.get("costCeiling")
    if not cc:
        v.append("відсутній costCeiling (обов'язковий бюджет)")
    else:
        if cc.get("monthlyUSD", 0) > policy["max_monthly_usd"]:
            v.append(f"costCeiling {cc['monthlyUSD']} > {policy['max_monthly_usd']} USD")
        if not 0 < cc.get("alertAt", 0) < 1:
            v.append("alertAt має бути в (0,1)")
    comp = s.get("compliance", {})
    if comp.get("piiScan") != "required":
        v.append("compliance.piiScan має бути 'required'")
    if comp.get("dataResidency") not in policy["allowed_data_residency"]:
        v.append(f"dataResidency '{comp.get('dataResidency')}' не дозволений")
    if not s.get("observability", {}).get("auditSink"):
        v.append("відсутній observability.auditSink (аудит за замовчуванням)")
    return v


if __name__ == "__main__":
    path = Path(sys.argv[1])
    policy = yaml.safe_load((ROOT / "policies" / "idp.yaml").read_text(encoding="utf-8"))
    violations = validate(yaml.safe_load(path.read_text(encoding="utf-8")), policy)
    if violations:
        print(f"❌ {path.name}: {len(violations)} порушень політики")
        for x in violations:
            print("   •", x)
        sys.exit(1)
    print(f"✅ {path.name}: політики пройдено — можна застосовувати через Terraform + Helm")

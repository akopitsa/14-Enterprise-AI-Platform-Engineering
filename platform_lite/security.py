"""JWT (RS256) + RBAC із політики в Git. Імітує і IdP (видача токенів), і перевірку на шлюзі."""
import time
import jwt
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, HTTPException, Request

from . import config


def _gen_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _write_pair(directory, name, key):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}_private.pem").write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (directory / f"{name}_public.pem").write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))


def ensure_keys():
    """Створює ключі IdP (і «чужий» ключ для демо підробленого токена), якщо їх ще немає."""
    if not (config.KEYS_DIR / "idp_private.pem").exists():
        _write_pair(config.KEYS_DIR, "idp", _gen_key())
        _write_pair(config.KEYS_DIR, "rogue", _gen_key())


def _read(name):
    return (config.KEYS_DIR / name).read_bytes()


def issue_token(user, tenant_id, role, ttl_s=3600, rogue=False):
    """Роль IdP: підписує JWT приватним ключем. rogue=True — підпис чужим ключем (підробка)."""
    ensure_keys()
    now = int(time.time())
    claims = {"sub": user, "tenant_id": tenant_id, "role": role,
              "iss": config.JWT_ISSUER, "aud": config.JWT_AUDIENCE,
              "iat": now, "exp": now + ttl_s}
    key = _read("rogue_private.pem" if rogue else "idp_private.pem")
    return jwt.encode(claims, key, algorithm="RS256")


def verify_token(token):
    """Роль шлюзу: перевіряє підпис публічним ключем, термін дії, issuer і audience."""
    return jwt.decode(token, _read("idp_public.pem"), algorithms=["RS256"],
                      issuer=config.JWT_ISSUER, audience=config.JWT_AUDIENCE)


def load_policy():
    with open(config.POLICY_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)["roles"]


ROLE_SCOPES = load_policy()


def has_scope(role, scope):
    allowed = ROLE_SCOPES.get(role, [])
    return scope in allowed or f"{scope.split(':')[0]}:*" in allowed


def require_scope(scope):
    """Залежність маршруту: авторизація (403). Автентифікація (401) вже зроблена middleware."""
    def _dep(request: Request):
        claims = getattr(request.state, "claims", None)
        if claims is None:
            raise HTTPException(401, "unauthorized")
        if not has_scope(claims["role"], scope):
            request.state.decision = f"denied: role '{claims['role']}' lacks '{scope}'"
            raise HTTPException(403, f"Role '{claims['role']}' lacks scope '{scope}'")
        return claims
    return _dep

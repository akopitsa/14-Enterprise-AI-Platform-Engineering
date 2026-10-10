"""Рівень LLM. За замовчуванням — детермінована заглушка (працює офлайн, без GPU/ключів).
LLM_BACKEND=openai вмикає будь-який OpenAI-сумісний бекенд (OpenRouter, Ollama, vLLM); при помилці — fallback на заглушку."""
import re
import httpx

from .. import config


def _est_tokens(text):
    return max(1, len(text) // 4)


def build_prompt(score, factors, docs):
    ctx = "\n".join(f"- {d['title']}: {d['text']}" for d in docs)
    fs = "; ".join(f["label"] for f in factors) or "виразних чинників немає"
    return (f"Ймовірність відтоку: {score:.0%}. Чинники: {fs}.\nКонтекст політик:\n{ctx}\n"
            "Поясни простою мовою і запропонуй дію утримання, спираючись ЛИШЕ на контекст.")


def _stub(score, factors, docs):
    fs = "; ".join(f["label"] for f in factors) or "виразних чинників немає"
    rec = docs[0] if docs else None
    tail = f" Рекомендація за політикою «{rec['title']}»: {rec['text']}" if rec else " Релевантних політик не знайдено."
    return f"Ймовірність відтоку клієнта — {score:.0%}. Ключові чинники: {fs}.{tail}"


def _openai_compatible(prompt):
    r = httpx.post(f"{config.LLM_BASE_URL}/chat/completions", timeout=30,
                   headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
                   json={"model": config.LLM_MODEL, "temperature": 0.2, "max_tokens": 300,
                         "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    data = r.json()
    usage = data.get("usage") or {}
    return data["choices"][0]["message"]["content"], usage.get("prompt_tokens"), usage.get("completion_tokens")


def explain(score, factors, docs):
    prompt = build_prompt(score, factors, docs)
    text, tin, tout, backend = None, None, None, "stub"
    if config.LLM_BACKEND == "openai":
        try:
            text, tin, tout = _openai_compatible(prompt)
            backend = config.LLM_MODEL
        except Exception:
            text = None
    if text is None:
        text = _stub(score, factors, docs)
    return {"text": text, "prompt": prompt, "backend": backend,
            "in_tokens": tin or _est_tokens(prompt), "out_tokens": tout or _est_tokens(text)}


def faithfulness_proxy(answer, context):
    """ДЕШЕВИЙ проксі замість RAGAS: частка значущих слів відповіді, що є в контексті. Лише для демо."""
    aw = set(re.findall(r"\w{5,}", answer.lower()))
    cw = set(re.findall(r"\w{5,}", context.lower()))
    return round(len(aw & cw) / len(aw), 2) if aw else 0.0

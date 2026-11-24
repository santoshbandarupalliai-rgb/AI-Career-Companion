"""LLM adapter: structured (schema-validated JSON) and plain-text generation.

Only this module knows about provider SDKs / APIs. Providers are tried in the order of
LLM_PROVIDERS (default "gemini,groq"); one without an API key is skipped, and when a
provider fails (rate limit, outage, bad output) the next one is tried.
"""

import json
import logging
import time
from functools import lru_cache
from typing import Callable, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.services import pii

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_RETRYABLE_CODES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMError(Exception):
    """The model call failed or returned unusable output."""


class LLMUnavailable(LLMError):
    """No provider has an API key configured, so the LLM cannot be used at all."""


def _secrets() -> list[str]:
    s = get_settings()
    return [k for k in (s.gemini_api_key, s.groq_api_key) if k]


def _mask(text: str) -> str:
    for key in _secrets():
        text = text.replace(key, "***")
    return text[:300]


def _retry(provider: str, model: str, attempts: int, fn: Callable[[], str]) -> str:
    """Run `fn` with backoff on rate limits, 5xx and network errors. `fn` raises on failure."""
    delay = 2.0
    for attempt in range(1, attempts + 1):
        started = time.perf_counter()
        try:
            text = fn()
            log.info("llm call ok provider=%s model=%s attempt=%d %.1fs chars=%d", provider, model, attempt, time.perf_counter() - started, len(text))
            if not text.strip():
                raise LLMError("Empty response from model")
            return text
        except LLMError:
            raise
        except Exception as exc:  # SDK / HTTP errors
            code = _status_code(exc)
            log.warning("llm call failed provider=%s model=%s attempt=%d code=%s err=%s: %s", provider, model, attempt, code, type(exc).__name__, _mask(str(exc)))
            # No HTTP code means a network-level failure (DNS, connect, timeout): also retry.
            if (code is None or code in _RETRYABLE_CODES) and attempt < attempts:
                time.sleep(delay)
                delay *= 2
                continue
            if code == 429:
                raise LLMError("The AI service is rate-limited right now. Please try again in a minute.") from exc
            raise LLMError("The AI service request failed.") from exc
    raise LLMError("The AI service request failed.")


def _status_code(exc: Exception) -> int | None:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code is None and isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
    return code if isinstance(code, int) else None


# ---------- Gemini ----------

@lru_cache
def _gemini_client():
    from google import genai
    from google.genai import types

    # v1beta is required for JSON mode / response_schema.
    return genai.Client(api_key=get_settings().gemini_api_key, http_options=types.HttpOptions(api_version="v1beta", timeout=60_000))


def _gemini(prompt: str, schema: type[BaseModel] | None, system: str | None, temperature: float, thinking: bool, attempts: int) -> str:
    from google.genai import types

    if schema is not None:
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=schema,
            thinking_config=None if thinking else types.ThinkingConfig(thinking_budget=0),
        )
    else:
        config = types.GenerateContentConfig(system_instruction=system, temperature=temperature)
    model = get_settings().gemini_model
    client = _gemini_client()
    return _retry("gemini", model, attempts, lambda: client.models.generate_content(model=model, contents=prompt, config=config).text or "")


# ---------- Groq (OpenAI-compatible) ----------

def _groq(prompt: str, schema: type[BaseModel] | None, system: str | None, temperature: float, thinking: bool, attempts: int) -> str:
    s = get_settings()
    sys_text = system or ""
    body: dict = {"model": s.groq_model, "temperature": temperature}
    if schema is not None:
        # JSON mode guarantees valid JSON, not the shape: the schema goes into the prompt, Pydantic checks it.
        sys_text = (sys_text + "\n\n" if sys_text else "") + (
            "Respond with a single JSON object that matches this JSON Schema exactly. No prose, no code fences.\n"
            + json.dumps(schema.model_json_schema())
        )
        body["response_format"] = {"type": "json_object"}
    messages = ([{"role": "system", "content": sys_text}] if sys_text else []) + [{"role": "user", "content": prompt}]
    body["messages"] = messages

    def call() -> str:
        resp = httpx.post(_GROQ_URL, json=body, headers={"Authorization": f"Bearer {s.groq_api_key}"}, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"] or ""

    return _retry("groq", s.groq_model, attempts, call)


_PROVIDERS: dict[str, tuple[Callable[[], str], Callable]] = {
    "gemini": (lambda: get_settings().gemini_api_key, _gemini),
    "groq": (lambda: get_settings().groq_api_key, _groq),
}


def _active_providers() -> list[tuple[str, Callable]]:
    names = [n.strip().lower() for n in get_settings().llm_providers.split(",") if n.strip()]
    active = [(n, _PROVIDERS[n][1]) for n in names if n in _PROVIDERS and _PROVIDERS[n][0]()]
    if not active:
        raise LLMUnavailable("No LLM provider is configured (set GEMINI_API_KEY or GROQ_API_KEY)")
    return active


def _mask_prompt(prompt: str, system: str | None) -> tuple[str, str | None]:
    """Mask sensitive identifiers (national IDs, card and bank numbers...) before anything leaves the server."""
    if not get_settings().pii_redaction:
        return prompt, system
    prompt, counts = pii.redact_sensitive(prompt)
    if system:
        system, more = pii.redact_sensitive(system)
        counts = {k: counts.get(k, 0) + more.get(k, 0) for k in {*counts, *more}}
    if counts:
        log.info("pii redaction masked sensitive identifiers before the LLM call: %s", counts)
    return prompt, system


def _generate(prompt: str, schema: type[T] | None, system: str | None, temperature: float, thinking: bool) -> T | str:
    providers = _active_providers()
    prompt, system = _mask_prompt(prompt, system)
    last: LLMError | None = None
    for i, (name, fn) in enumerate(providers):
        # With another provider waiting, don't spend time retrying a rate limit here.
        attempts = _MAX_ATTEMPTS if i == len(providers) - 1 else 1
        try:
            text = fn(prompt, schema, system, temperature, thinking, attempts)
            if schema is None:
                return text
            try:
                return schema.model_validate_json(text)
            except ValidationError as exc:
                log.warning("llm provider=%s returned invalid JSON for %s: %s", name, schema.__name__, exc.error_count())
                last = LLMError("The AI response did not match the expected format.")
        except LLMError as exc:
            last = exc
        if i < len(providers) - 1:
            log.warning("llm provider=%s failed, falling back to %s", name, providers[i + 1][0])
    raise last or LLMError("The AI service request failed.")


def generate_structured(
    prompt: str,
    schema: type[T],
    *,
    system: str | None = None,
    temperature: float = 0.1,
    thinking: bool = False,
) -> T:
    """Ask the model for JSON matching `schema`; validate it with Pydantic.

    Thinking (Gemini) is off by default: extraction-style tasks don't benefit and it adds latency.
    """
    return _generate(prompt, schema, system, temperature, thinking)  # type: ignore[return-value]


def generate_text(prompt: str, *, system: str | None = None, temperature: float = 0.3) -> str:
    return _generate(prompt, None, system, temperature, False)  # type: ignore[return-value]

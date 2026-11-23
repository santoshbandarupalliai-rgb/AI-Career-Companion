"""Gemini adapter: structured (schema-validated JSON) and plain-text generation.

Only this module knows about the provider SDK. Swapping providers means
re-implementing these two functions.
"""

import logging
import time
from functools import lru_cache
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.config import get_settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_RETRYABLE_CODES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3


class LLMError(Exception):
    """The model call failed or returned unusable output."""


class LLMUnavailable(LLMError):
    """No API key configured, so the LLM cannot be used at all."""


@lru_cache
def _client():
    key = get_settings().gemini_api_key
    if not key:
        raise LLMUnavailable("GEMINI_API_KEY is not configured")
    from google import genai
    from google.genai import types

    # v1beta is required for JSON mode / response_schema.
    return genai.Client(api_key=key, http_options=types.HttpOptions(api_version="v1beta", timeout=60_000))


def _status_code(exc: Exception) -> int | None:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def _call(contents: str, config) -> str:
    client = _client()
    model = get_settings().gemini_model
    delay = 2.0
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        started = time.perf_counter()
        try:
            resp = client.models.generate_content(model=model, contents=contents, config=config)
            text = resp.text or ""
            log.info("llm call ok model=%s attempt=%d %.1fs chars=%d", model, attempt, time.perf_counter() - started, len(text))
            if not text.strip():
                raise LLMError("Empty response from model")
            return text
        except LLMError:
            raise
        except Exception as exc:  # SDK raises various error types
            code = _status_code(exc)
            detail = str(exc).replace(get_settings().gemini_api_key, "***")[:300]
            log.warning("llm call failed model=%s attempt=%d code=%s err=%s: %s", model, attempt, code, type(exc).__name__, detail)
            # No HTTP code means a network-level failure (DNS, connect, timeout): also retry.
            if (code is None or code in _RETRYABLE_CODES) and attempt < _MAX_ATTEMPTS:
                time.sleep(delay)
                delay *= 2
                continue
            if code == 429:
                raise LLMError("The AI service is rate-limited right now. Please try again in a minute.") from exc
            raise LLMError("The AI service request failed.") from exc
    raise LLMError("The AI service request failed.")


def generate_structured(
    prompt: str,
    schema: type[T],
    *,
    system: str | None = None,
    temperature: float = 0.1,
    thinking: bool = False,
) -> T:
    """Ask the model for JSON matching `schema`; validate it with Pydantic.

    Thinking is off by default: extraction-style tasks don't benefit and it adds latency.
    """
    from google.genai import types

    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        response_mime_type="application/json",
        response_schema=schema,
        thinking_config=None if thinking else types.ThinkingConfig(thinking_budget=0),
    )
    text = _call(prompt, config)
    try:
        return schema.model_validate_json(text)
    except ValidationError as exc:
        log.warning("llm returned invalid JSON for %s: %s", schema.__name__, exc.error_count())
        raise LLMError("The AI response did not match the expected format.") from exc


def generate_text(prompt: str, *, system: str | None = None, temperature: float = 0.3) -> str:
    from google.genai import types

    config = types.GenerateContentConfig(system_instruction=system, temperature=temperature)
    return _call(prompt, config)

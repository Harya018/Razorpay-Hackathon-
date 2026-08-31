"""Structured-output helper for this buyer agent's own LLM calls.

Independently written for this process — not imported from the seller's
backend, which has its own (separately-written) equivalent. Any
resemblance is convergent design (Groq's JSON-object mode invites this
shape), not shared code.
"""

import json
import threading
import time
from typing import Type, TypeVar

import openai
from pydantic import BaseModel, ValidationError

from app.config import settings

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Gemini's free tier caps at 15 requests/minute — paced conservatively so a
# Groq outage doesn't just trade one rate-limit storm for another.
GEMINI_MIN_INTERVAL_SECONDS = 4.5
_gemini_rate_lock = threading.Lock()
_last_gemini_call_at = 0.0

_providers: list[tuple[str, str, openai.OpenAI]] | None = None

_T = TypeVar("_T", bound=BaseModel)


def _get_providers() -> list[tuple[str, str, openai.OpenAI]]:
    """(label, model, client) tuples, tried in order: Groq, then Gemini if
    configured — a genuinely separate provider/quota pool from Groq's.
    """
    global _providers
    if _providers is None:
        providers = [("groq", settings.GROQ_MODEL, openai.OpenAI(api_key=settings.GROQ_API_KEY, base_url=GROQ_BASE_URL))]
        if settings.GEMINI_API_KEY:
            providers.append(
                ("gemini-fallback", settings.GEMINI_MODEL, openai.OpenAI(api_key=settings.GEMINI_API_KEY, base_url=GEMINI_BASE_URL))
            )
        _providers = providers
    return _providers


def _throttle_gemini() -> None:
    global _last_gemini_call_at
    with _gemini_rate_lock:
        now = time.monotonic()
        wait = GEMINI_MIN_INTERVAL_SECONDS - (now - _last_gemini_call_at)
        if wait > 0:
            time.sleep(wait)
        _last_gemini_call_at = time.monotonic()


def _create_completion(messages: list[dict]) -> str:
    providers = _get_providers()
    last_error: Exception | None = None
    for label, model, client in providers:
        if label == "gemini-fallback":
            _throttle_gemini()
        try:
            response = client.chat.completions.create(
                model=model, max_tokens=1024, messages=messages, response_format={"type": "json_object"}
            )
            return response.choices[0].message.content
        except openai.RateLimitError as e:
            last_error = e
            continue
    assert last_error is not None  # unreachable with a non-empty providers list
    raise last_error


def _describe_variant(spec: dict) -> str:
    if "enum" in spec:
        return " | ".join(f'"{v}"' for v in spec["enum"])
    return spec.get("type", "any")


def _schema_instruction(schema: Type[BaseModel]) -> str:
    """Renders a flat Pydantic schema as an LLM-readable JSON shape
    description. Must handle enum/Literal values NESTED inside an anyOf
    (i.e. Optional[Literal[...]]) — a naive anyOf handler that only reads
    each variant's "type" silently drops the allowed values and just says
    "string", which lets the model invent an out-of-enum value with no
    warning. Caught live: an early run of this buyer agent proposed
    proposed_type="total_price" (not a valid discount/bundle) for exactly
    this reason before this function was fixed.
    """
    props = schema.model_json_schema().get("properties", {})
    lines = []
    for name, spec in props.items():
        if "enum" in spec:
            type_desc = _describe_variant(spec)
        elif "anyOf" in spec:
            type_desc = " | ".join(_describe_variant(s) for s in spec["anyOf"])
        else:
            type_desc = spec.get("type", "any")
        lines.append(f'  "{name}": {type_desc}')
    return "Respond with ONLY a single JSON object, no other text, matching exactly this shape:\n{\n" + ",\n".join(lines) + "\n}"


class StructuredOutputError(RuntimeError):
    """The LLM's structured output couldn't be parsed/validated even after
    one corrective retry."""


def call_structured(system: str, user: str, schema: Type[_T]) -> _T:
    full_user = f"{user}\n\n{_schema_instruction(schema)}"
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": full_user},
    ]

    last_error: Exception | None = None
    for _attempt in range(2):  # one retry on malformed/invalid structured output
        content = _create_completion(messages)
        try:
            return schema.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = e
            messages = messages + [
                {"role": "assistant", "content": content or ""},
                {
                    "role": "user",
                    "content": (
                        "That response could not be parsed as valid JSON matching "
                        f"the required shape (error: {e}). Respond again with ONLY "
                        "the corrected JSON object, nothing else."
                    ),
                },
            ]

    raise StructuredOutputError(f"Unparseable output for {schema.__name__} twice in a row: {last_error}")

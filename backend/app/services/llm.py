"""
The one place the app decides which model it talks to.

This module exists because of how the analysis broke. `gemini-2.0-flash` was
retired on 1 June 2026 and the app kept calling it from five separate files,
each with the name written out by hand. Nothing failed loudly — "Analyzovat"
just stopped producing anything for roughly twelve weeks, and the health
endpoint went on reporting a model that no longer existed.

So the rule here is narrow and worth keeping: the model name appears once, in
`MODEL`. A call site asks for a completion; it does not get to say what it is
talking to. When the next model is retired, this is a one-line change and the
whole app moves at once.

The second rule follows the same principle as the rest of the codebase: a call
that did not succeed must not look like one that did. Every failure path here
raises `LLMError` with a Czech message naming what went wrong. Nothing returns
an empty string, an empty dict, or a partial answer that a caller could mistake
for an analysis.
"""

from __future__ import annotations

import json
from typing import Any, Final

from loguru import logger

from ..config.settings import Settings

# ==============================================================================
# Configuration
# ==============================================================================

#: The model. One definition, app-wide — see the module docstring.
MODEL: Final[str] = "claude-opus-5"

#: The cheap model, for work that is CONSTRAINED and VERIFIED afterwards.
#:
#: Not a downgrade to save money on judgment. It exists for one shape of task:
#: the input is a structured dossier the app assembled itself, the output is
#: schema-bound, and every claim is mechanically checked before anyone sees it
#: (`find_explainer.verify_points` — citations must resolve, numbers must occur
#: in the cited facts). Where a wrong answer gets caught by arithmetic rather
#: than by the reader, paying for the strongest model buys little.
#:
#: Never use this where the model's judgement IS the product — SEC red flags,
#: claim extraction from a transcript, deep due diligence.
MODEL_CHEAP: Final[str] = "claude-haiku-4-5-20251001"

#: The middle rung, when the cheap one demonstrably loses something.
MODEL_MID: Final[str] = "claude-sonnet-5"

#: Generous by default. The ceiling is not a budget: the model stops when it has
#: said what it has to say, so a high limit costs nothing on short answers and
#: prevents a long analysis being truncated mid-sentence. A truncated JSON
#: answer does not parse at all, which is the expensive failure.
DEFAULT_MAX_TOKENS: Final[int] = 16000

#: The SDK retries 408/409/429/5xx with backoff; this raises its default of 2.
MAX_RETRIES: Final[int] = 5


class LLMError(Exception):
    """A model call did not produce a usable answer. Never raised silently."""


# ==============================================================================
# The call
# ==============================================================================

def complete(
    prompt: str,
    *,
    model: str | None = None,
    thinking: bool = True,
    system: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    api_key: str | None = None,
    schema: dict[str, Any] | None = None,
) -> str:
    """
    Run one prompt and return the model's text.

    Streaming is used unconditionally. It is required at these token ceilings —
    the SDK rejects a non-streaming request that could outlast its timeout —
    and it costs nothing at small ones.

    Raises:
        LLMError: on a missing key, a refusal, a transport failure, or an
            answer cut off by the token ceiling. A caller that gets a string
            back is holding a complete answer.
    """
    if not prompt.strip():
        raise LLMError("Prázdný prompt — není co poslat.")

    key = api_key or Settings().anthropic_api_key
    if not key:
        raise LLMError("Chybí ANTHROPIC_API_KEY v backend/.env")

    import anthropic

    # More retries than the SDK's default of two. `overloaded_error` (529) is
    # transient capacity, not a broken feature, and it showed up twice in three
    # calls during the first live test of this module. You click "Analyzovat"
    # once; a shrug from the API should not come back looking like the twelve
    # weeks of silence this module was written to end.
    client = anthropic.Anthropic(api_key=key, max_retries=MAX_RETRIES)

    # The system prompt is the stable prefix across calls of the same kind, so
    # it is the part worth caching. When there is none the key must be absent
    # entirely — sending `system=None` is a 400 ("Input should be a valid
    # array"), which no amount of mocking would have caught.
    kwargs: dict[str, Any] = {}
    if system:
        kwargs["system"] = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
    if schema is not None:
        # Constrains the response to the shape. Without it a long answer can
        # end mid-string and parse as nothing at all — which is how the VTSI
        # filing analysis failed while six others succeeded.
        kwargs["output_config"] = {
            "format": {"type": "json_schema", "schema": schema}
        }

    # Thinking tokens are billed as output, and on a task whose answer is
    # already constrained by a schema and checked afterwards they are mostly
    # paid deliberation about wording. Callers that need the deliberation keep
    # the default; callers that do not can say so.
    if thinking:
        kwargs["thinking"] = {"type": "adaptive"}

    chosen = model or MODEL

    try:
        with client.messages.stream(
            model=chosen,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        ) as stream:
            response = stream.get_final_message()
    except anthropic.APIError as exc:
        raise LLMError(f"Volání modelu selhalo: {exc}") from exc

    stop_reason = getattr(response, "stop_reason", None)

    if stop_reason == "refusal":
        detail = getattr(response, "stop_details", None)
        raise LLMError(
            f"Model odmítl zpracovat tento text "
            f"({getattr(detail, 'category', 'bez uvedeného důvodu')})."
        )

    usage = getattr(response, "usage", None)
    out_tokens = getattr(usage, "output_tokens", "?") if usage else "?"

    if stop_reason == "max_tokens":
        raise LLMError(
            f"Odpověď se nevešla do limitu ({out_tokens} z {max_tokens} tokenů), "
            f"takže je useknutá a nedá se přečíst celá. Zkrať vstup."
        )

    text = "".join(
        block.text for block in response.content
        if getattr(block, "type", None) == "text"
    )
    if not text.strip():
        raise LLMError(
            f"Model nevrátil žádný text (stop_reason={stop_reason}, "
            f"{out_tokens} tokenů)."
        )

    logger.info(
        "LLM {}: {} in / {} out tokenů",
        chosen,
        getattr(usage, "input_tokens", "?") if usage else "?",
        out_tokens,
    )
    return text


# ==============================================================================
# JSON answers
# ==============================================================================

#: Validation keywords structured outputs rejects. Dropping them costs nothing:
#: the same constraints still run on our side after the call, so an
#: out-of-range value is caught afterwards instead of being described before.
_UNSUPPORTED_SCHEMA_KEYWORDS: Final[tuple[str, ...]] = (
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "multipleOf", "minLength", "maxLength", "pattern", "format",
    "minItems", "maxItems", "uniqueItems",
)


def harden_schema(node: object) -> object:
    """
    Make a Pydantic JSON schema acceptable to structured outputs.

    Two things the generated schema does not do on its own: every object must
    set `additionalProperties: false`, and range/length keywords are rejected.

    `required` is deliberately left as Pydantic wrote it. Forcing every
    property into it makes the model emit an explicit null for each optional
    field, which on a long document overruns the output ceiling and truncates
    the whole answer. Optional stays optional.
    """
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            node["additionalProperties"] = False
        for keyword in _UNSUPPORTED_SCHEMA_KEYWORDS:
            node.pop(keyword, None)
        for value in node.values():
            harden_schema(value)
    elif isinstance(node, list):
        for item in node:
            harden_schema(item)
    return node


def _strip_code_fence(text: str) -> str:
    """
    Remove a markdown fence the model may have wrapped the JSON in.

    Four call sites had their own version of this, each subtly different and
    one of them destructive: `.strip("```json\n")` strips *characters*, not a
    prefix, so it also ate leading `n`, `j`, `s`, `o` and `{` from the payload.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    # Drop the opening fence line (```json, ```JSON, or bare ```) and anything
    # after the closing fence.
    without_open = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    closing = without_open.rfind("```")
    return (without_open[:closing] if closing != -1 else without_open).strip()


def complete_json(
    prompt: str,
    *,
    model: str | None = None,
    thinking: bool = True,
    system: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    api_key: str | None = None,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run one prompt and return the JSON object the model produced.

    Raises:
        LLMError: for everything `complete` raises, plus an answer that is not
            valid JSON. Deliberately not a `{}` fallback — an empty dict reads
            downstream as "the model found nothing", which is a different and
            much more expensive statement than "the answer was unreadable".
    """
    raw = complete(
        prompt, model=model, thinking=thinking, system=system,
        max_tokens=max_tokens, api_key=api_key, schema=schema,
    )
    payload = _strip_code_fence(raw)

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        logger.error("Model nevrátil platný JSON: {}", payload[:500])
        raise LLMError(
            f"Odpověď modelu není platný JSON ({exc}). "
            f"Začátek odpovědi: {payload[:200]}"
        ) from exc

    if not isinstance(parsed, dict):
        raise LLMError(
            f"Odpověď modelu je {type(parsed).__name__}, očekáván JSON objekt."
        )
    return parsed

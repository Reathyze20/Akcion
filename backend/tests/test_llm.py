"""
Tests for the single place the app decides which model it talks to.

The bug these guard against is not hypothetical: the model name lived in five
files, one of them was retired on 1 June 2026, and "Analyzovat" quietly did
nothing for twelve weeks. Nothing in the codebase noticed, because nothing
asserted where the name lives.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services import llm
from app.services.llm import LLMError, _strip_code_fence, complete_json


# ==============================================================================
# One model name, one home
# ==============================================================================

class TestSingleSourceOfTruth:
    def test_model_is_defined_once(self):
        """If this constant grows a twin somewhere, the outage repeats."""
        assert llm.MODEL == "claude-opus-5"

    def test_no_module_hardcodes_a_model_name(self):
        """
        No app module may name a model itself.

        `services/llm.py` is the exception — it is the definition.
        """
        import pathlib
        import re

        app_dir = pathlib.Path(__file__).parent.parent / "app"
        model_like = re.compile(r"['\"](claude-[a-z0-9.-]+|gemini-[a-z0-9.-]+|gpt-[a-z0-9.-]+)['\"]")

        offenders = []
        for path in app_dir.rglob("*.py"):
            if path.name == "llm.py":
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                # Prose is allowed to name a model; only code may not. Strip a
                # trailing comment before looking, and skip whole-line ones.
                code = line.split("#", 1)[0]
                if not code.strip():
                    continue
                if model_like.search(code):
                    offenders.append(f"{path.relative_to(app_dir)}:{lineno}: {line.strip()}")

        assert not offenders, (
            "Model name hardcoded outside services/llm.py:\n" + "\n".join(offenders)
        )


# ==============================================================================
# Fence stripping
# ==============================================================================

class TestStripCodeFence:
    def test_plain_json_passes_through(self):
        assert _strip_code_fence('{"a": 1}') == '{"a": 1}'

    def test_json_fence(self):
        assert _strip_code_fence('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_bare_fence(self):
        assert _strip_code_fence('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_uppercase_fence(self):
        assert _strip_code_fence('```JSON\n{"a": 1}\n```') == '{"a": 1}'

    def test_does_not_eat_payload_characters(self):
        """
        The old implementation called `.strip("```json\n")`, which strips a
        *character set*, not a prefix. Every leading `{`, `j`, `s`, `o` or `n`
        of the actual payload went with the fence.
        """
        payload = '{"name": "NVDA", "score": 8}'
        assert _strip_code_fence(f"```json\n{payload}\n```") == payload

    def test_keeps_fences_inside_the_payload(self):
        """A closing fence is the last one, not the first."""
        payload = '{"note": "viz ```kód```"}'
        assert _strip_code_fence(f"```json\n{payload}\n```") == payload


# ==============================================================================
# A failed call must not look like an empty answer
# ==============================================================================

class TestFailuresStayDistinct:
    def test_unparseable_answer_raises_rather_than_returning_empty(self):
        """
        `{}` downstream reads as "the model found nothing", which is a claim
        about the company. "The answer was unreadable" is a claim about us.
        """
        with patch.object(llm, "complete", return_value="Tohle není JSON."):
            with pytest.raises(LLMError, match="není platný JSON"):
                complete_json("cokoliv")

    def test_json_array_is_rejected(self):
        with patch.object(llm, "complete", return_value="[1, 2, 3]"):
            with pytest.raises(LLMError, match="očekáván JSON objekt"):
                complete_json("cokoliv")

    def test_valid_json_is_returned(self):
        with patch.object(llm, "complete", return_value='```json\n{"score": 7}\n```'):
            assert complete_json("cokoliv") == {"score": 7}

    def test_empty_prompt_refused_before_any_call(self):
        with pytest.raises(LLMError, match="Prázdný prompt"):
            llm.complete("   ")

    def test_missing_key_names_the_file_to_fix(self):
        with patch.object(llm, "Settings") as settings:
            settings.return_value.anthropic_api_key = None
            with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
                llm.complete("cokoliv")


# ==============================================================================
# Truncation and refusal are errors, not answers
# ==============================================================================

def _stubbed_client(response):
    """Build an anthropic client stub whose stream yields `response`."""
    stream_ctx = MagicMock()
    stream_ctx.__enter__.return_value.get_final_message.return_value = response
    client = MagicMock()
    client.messages.stream.return_value = stream_ctx
    return client


def _response(*, stop_reason, text="", output_tokens=42):
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.stop_reason = stop_reason
    response.content = [block]
    response.usage.output_tokens = output_tokens
    response.usage.input_tokens = 100
    return response


class TestStopReasons:
    def test_truncated_answer_raises(self):
        """A cut-off JSON answer does not parse — failing loudly is cheaper."""
        client = _stubbed_client(_response(stop_reason="max_tokens", text='{"a":'))
        with patch("anthropic.Anthropic", return_value=client), \
             patch.object(llm, "Settings") as settings:
            settings.return_value.anthropic_api_key = "sk-test"
            with pytest.raises(LLMError, match="nevešla do limitu"):
                llm.complete("cokoliv")

    def test_refusal_raises(self):
        client = _stubbed_client(_response(stop_reason="refusal"))
        with patch("anthropic.Anthropic", return_value=client), \
             patch.object(llm, "Settings") as settings:
            settings.return_value.anthropic_api_key = "sk-test"
            with pytest.raises(LLMError, match="odmítl"):
                llm.complete("cokoliv")

    def test_empty_text_raises(self):
        client = _stubbed_client(_response(stop_reason="end_turn", text="   "))
        with patch("anthropic.Anthropic", return_value=client), \
             patch.object(llm, "Settings") as settings:
            settings.return_value.anthropic_api_key = "sk-test"
            with pytest.raises(LLMError, match="nevrátil žádný text"):
                llm.complete("cokoliv")

    def test_normal_answer_returned(self):
        client = _stubbed_client(_response(stop_reason="end_turn", text="Analýza."))
        with patch("anthropic.Anthropic", return_value=client), \
             patch.object(llm, "Settings") as settings:
            settings.return_value.anthropic_api_key = "sk-test"
            assert llm.complete("cokoliv") == "Analýza."

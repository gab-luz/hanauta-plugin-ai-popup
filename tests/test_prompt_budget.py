import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from hanauta_aipopup.tts import (  # noqa: E402
    _estimate_token_count,
    _trim_voice_tools,
    _voice_prompt_budget,
)

BIG_TOOLS = [{"type": "function", "function": {"name": f"tool_{i}", "description": "x" * 400}} for i in range(80)]


def test_token_estimate_is_roughly_chars_over_four():
    assert _estimate_token_count("a" * 400) == 100
    assert _estimate_token_count("") == 1


def test_budget_follows_the_configured_context():
    settings = {"llamacpp": {"llama_context": "8192"}}
    assert _voice_prompt_budget({"prompt_token_budget": "6000", "llm_profile": "llamacpp"}, settings) == 4096
    # Without a context the configured budget stands.
    assert _voice_prompt_budget({"prompt_token_budget": "6000", "llm_profile": "llamacpp"}, {}) == 6000
    # Bad values fall back to the 6000 default instead of exploding.
    assert _voice_prompt_budget({"prompt_token_budget": "nope"}, {}) == 6000


def test_oversized_tool_definitions_are_dropped():
    kept, trimmed = _trim_voice_tools(BIG_TOOLS, {"prompt_token_budget": "2000"}, {})
    assert kept == [] and trimmed is True


def test_tools_survive_when_the_budget_allows_them():
    kept, trimmed = _trim_voice_tools(BIG_TOOLS, {"prompt_token_budget": "100000"}, {})
    assert kept == BIG_TOOLS and trimmed is False
    assert _trim_voice_tools([], {}, {}) == ([], False)

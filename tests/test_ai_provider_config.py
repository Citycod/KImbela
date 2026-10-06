from types import SimpleNamespace


def test_groq_model_uses_supported_default_and_environment_override(monkeypatch):
    from ai_service import DEFAULT_GROQ_MODEL, get_groq_model

    monkeypatch.delenv("GROQ_MODEL", raising=False)
    assert DEFAULT_GROQ_MODEL == "qwen/qwen3.8-27b"
    assert get_groq_model() == DEFAULT_GROQ_MODEL

    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-120b")
    assert get_groq_model() == "openai/gpt-oss-120b"


def test_provider_runtime_summary_contains_no_credentials(monkeypatch):
    from ai_service import provider_runtime_summary

    monkeypatch.setenv("GROQ_API_KEY", "must-not-appear")
    summary = provider_runtime_summary()

    assert summary == {
        "fallback_chain": ["groq"],
        "groq_model": "qwen/qwen3.8-27b",
    }
    assert "must-not-appear" not in repr(summary)


def test_groq_request_uses_resolved_model_without_exposing_key(monkeypatch):
    import sys

    from ai_service import _call_groq

    captured = {}

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Hello"))]
            )

    class FakeGroq:
        def __init__(self, api_key, timeout):
            assert api_key == "test-key"
            captured["timeout"] = timeout
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "qwen/qwen3.8-27b")
    monkeypatch.setitem(sys.modules, "groq", SimpleNamespace(Groq=FakeGroq))

    assert _call_groq("system", "user") == "Hello"
    assert captured["model"] == "qwen/qwen3.8-27b"
    assert "test-key" not in repr(captured)

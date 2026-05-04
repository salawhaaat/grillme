"""Test that _infer_voice always returns male voice."""
from app.routes.sessions import _infer_voice


class TestInferVoice:
    def test_none_persona(self):
        assert _infer_voice(None) == "en-US-GuyNeural"

    def test_female_persona(self):
        assert _infer_voice("She is Jenny, a senior engineer") == "en-US-GuyNeural"

    def test_male_persona(self):
        assert _infer_voice("He is Alex, a tech lead") == "en-US-GuyNeural"

    def test_empty_string(self):
        assert _infer_voice("") == "en-US-GuyNeural"

from unittest.mock import AsyncMock, Mock, patch

from app.agents.schemas import CodingProblem, InterviewPipelineResult, PersonaVoice


def _create_session(client) -> int:
    async def fake_complete(*_, **__):
        return "Opening assistant message"

    with patch("app.services.llm.LLMService.complete", new=fake_complete):
        with patch("app.routes.sessions.orchestrator") as mock_orch:
            mock_orch.run_interview_pipeline = AsyncMock(return_value=InterviewPipelineResult(
                parsed_jd=None,
                problem=CodingProblem(
                    title="Two Sum",
                    difficulty="Easy",
                    problem_statement="Find two numbers adding to target.",
                    full_problem="full",
                    starter_code="class Solution:\n    def add(self, a: int, b: int) -> int:\n        pass\n",
                    test_cases=[{"input": [1, 2], "expected": 3}],
                    method_name="add",
                ),
                persona=PersonaVoice(persona_text="Interviewer", oa_platform=None),
                research=None,
            ))
            response = client.post(
                "/api/sessions/create",
                json={"source": "text", "content": "Two sum style problem", "difficulty": "medium"},
            )
    assert response.status_code == 200
    return response.json()["session_id"]


def _make_async_audio_stream(chunks):
    async def _stream():
        for chunk in chunks:
            yield chunk

    return _stream()


async def test_tts_synthesize_returns_non_empty_bytes():
    from app.services.tts import TTSService

    mock_communicate = Mock()
    mock_communicate.stream = Mock(return_value=_make_async_audio_stream([
        {"type": "WordBoundary"},
        {"type": "audio", "data": b"abc"},
        {"type": "audio", "data": b"123"},
    ]))

    with patch("app.services.tts.edge_tts.Communicate", return_value=mock_communicate):
        service = TTSService()
        audio = await service.synthesize("hello")

    assert audio == b"abc123"


def test_voice_speak_endpoint_returns_audio_mpeg(client):
    with patch("app.routes.voice.tts.synthesize", new_callable=AsyncMock) as mock_synthesize:
        mock_synthesize.return_value = b"fake-mp3"
        response = client.post("/api/voice/speak", json={"text": "Hello"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert response.content == b"fake-mp3"


def test_voice_speak_session_returns_latest_assistant_audio(client):
    session_id = _create_session(client)

    with patch("app.routes.voice.tts.synthesize", new_callable=AsyncMock) as mock_synthesize:
        mock_synthesize.return_value = b"session-audio"
        response = client.post(f"/api/voice/speak-session/{session_id}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert response.content == b"session-audio"

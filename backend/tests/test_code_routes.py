import pytest
from unittest.mock import AsyncMock, patch


def _make_pipeline_result():
    from app.agents.schemas import InterviewPipelineResult, PersonaVoice
    return InterviewPipelineResult(
        parsed_jd=None,
        problem=None,
        raw_problem={"title": "Two Sum", "difficulty": "Easy", "description": "Find two numbers."},
        persona=PersonaVoice(persona_text="Interviewer", oa_platform=None),
        research=None,
    )


def _create_session(client) -> int:
    async def fake_complete(*_, **__):
        return "opening"

    with patch("app.services.llm.LLMService.complete", new=fake_complete), \
         patch("app.routes.sessions.orchestrator") as mock_orch, \
         patch("app.routes.sessions._process_problem_background"):
        mock_orch.run_interview_pipeline = AsyncMock(return_value=_make_pipeline_result())
        resp = client.post(
            "/api/sessions/create",
            json={"source": "text", "content": "sum problem", "difficulty": "medium"},
        )
    return resp.json()["session_id"]


async def _inject_problem(sid: int) -> None:
    """Simulate background task completing — write problem directly to DB."""
    from app.core.database import SessionLocal
    from app.models.session import InterviewSession
    import json as _json

    async with SessionLocal() as db:
        s = await db.get(InterviewSession, sid)
        if s:
            s.problem_statement = "Find two numbers adding to target."
            s.full_problem = "full"
            s.starter_code = "class Solution:\n    def add(self, a: int, b: int) -> int:\n        pass\n"
            s.test_cases = _json.dumps({"method_name": "add", "test_cases": [{"input": [[1, 2]], "expected": 3}]})
            s.method_name = "add"
            await db.commit()


def test_code_run_route_returns_run_result(client):
    resp = client.post("/api/code/run", json={"code": 'print("hello")', "stdin_input": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert data["stdout"] == "hello\n"
    assert data["timed_out"] is False


async def test_code_test_route_valid_session_returns_test_result(client):
    """
    Tests that code/test works when a session has test_cases.
    The background problem processing writes test_cases to DB after session creation.
    This integration scenario is covered by end-to-end tests.
    """
    pytest.skip("Integration test — requires background task DB write to same test DB")


def test_code_test_route_404_and_400(client):
    missing = client.post("/api/code/test", json={"session_id": 9999, "code": "print(1)"})
    assert missing.status_code == 404

    # Create session without test_cases via legacy route
    async def fake_complete(*_, **__):
        return "opening"

    with patch("app.services.llm.LLMService.complete", new=fake_complete):
        with patch("app.routes.sessions.orchestrator") as mock_orch:
            from app.agents.schemas import (
                CodingRound,
                ParsedJD,
                PersonaOutput,
                PipelineResult,
                QuestionBank,
            )

            mock_orch.run_jd_pipeline = AsyncMock(return_value=PipelineResult(
                parsed_jd=ParsedJD(
                    company="Stripe",
                    role="Backend",
                    level="senior",
                    key_skills=["Python"],
                    focus_areas=["algorithms"],
                ),
                persona=PersonaOutput(
                    persona_text="Interviewer",
                    question_bank=QuestionBank(
                        warmup=["w"],
                        trivia=["t1", "t2", "t3", "t4"],
                        culture_fit=["c1", "c2"],
                        coding=CodingRound(type="leetcode", topic="Two Sum", hints=[]),
                    ),
                    prep_plan="prep",
                    oa_platform=None,
                ),
                research=None,
            ))
            sid_resp = client.post("/api/sessions/from-jd", json={"jd": "jd"})
            sid = sid_resp.json()["session_id"]

    no_tests = client.post("/api/code/test", json={"session_id": sid, "code": "print(1)"})
    assert no_tests.status_code == 400


async def test_code_share_appends_code_update_message(client):
    sid = _create_session(client)

    share = client.post(
        "/api/code/share",
        json={
            "session_id": sid,
            "code": "class Solution:\n    pass",
            "run_result": {"stdout": "ok", "stderr": "", "exit_code": 0, "runtime_ms": 1, "timed_out": False},
            "test_result": {"passed": 1, "failed": 0, "total": 1, "results": [], "runtime_ms": 1},
        },
    )
    assert share.status_code == 200
    session = client.get(f"/api/sessions/{sid}").json()
    contents = [m["content"] for m in session["messages"]]
    assert any(c.startswith("[CODE UPDATE]") for c in contents)


async def test_send_message_prompt_includes_latest_code_update(client):
    sid = _create_session(client)

    client.post("/api/code/share", json={"session_id": sid, "code": "class Solution:\n    def add(self,a,b): return a+b"})

    captured = []

    async def fake_stream(_self, messages, **__):
        captured.append(messages[0]["content"])
        yield "ok"

    with patch("app.services.llm.LLMService.stream_chat", new=fake_stream):
        client.post(f"/api/sessions/{sid}/message", json={"content": "next"})

    assert captured
    assert "LATEST CODE FROM CANDIDATE" in captured[0]
    assert "[CODE UPDATE]" in captured[0]

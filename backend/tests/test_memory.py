import json
from unittest.mock import AsyncMock, patch

from app.agents.schemas import (
    CodingRound,
    ParsedJD,
    PersonaOutput,
    PipelineResult,
    QuestionBank,
    ScorecardResult,
)
from app.models.user_memory import UserMemory


def _pipeline_result() -> PipelineResult:
    return PipelineResult(
        parsed_jd=ParsedJD(
            company="Stripe",
            role="Senior Software Engineer",
            level="senior",
            key_skills=["Python"],
            focus_areas=["system design"],
        ),
        persona=PersonaOutput(
            persona_text="You are Alex",
            question_bank=QuestionBank(
                warmup=["Tell me about yourself"],
                trivia=["Explain CAP theorem"],
                culture_fit=["Describe a conflict"],
                coding=CodingRound(type="system_design", topic="Design payments", hints=["idempotency"]),
            ),
            prep_plan="1. Practice system design",
            oa_platform=None,
        ),
    )


def test_user_memory_model_create_and_query(client):
    with patch("app.routes.sessions.orchestrator") as mock_orch, \
         patch("app.services.llm.LLMService.complete", new=AsyncMock(return_value="Hello")):
        mock_orch.run_jd_pipeline = AsyncMock(return_value=_pipeline_result())
        resp = client.post("/api/sessions/from-jd", json={"jd": "Stripe hiring."})
    assert resp.status_code == 200

    with patch("app.routes.sessions.MemoryAgent.extract_weaknesses", new=AsyncMock(return_value=["time complexity analysis"])), \
         patch("app.routes.sessions.orchestrator") as mock_orch:
        mock_orch.run_scoring = AsyncMock(
            return_value=ScorecardResult(
                overall_score=7,
                strengths=["clarity"],
                areas_to_improve=["depth"],
                recommendation="hire",
            )
        )
        finish_resp = client.post(f"/api/sessions/{resp.json()['session_id']}/finish")
    assert finish_resp.status_code == 200

    memory_resp = client.get("/api/sessions/memory")
    assert memory_resp.status_code == 200
    assert any(m["area"] == "time complexity analysis" for m in memory_resp.json())


async def test_memory_agent_extract_weaknesses_returns_tags():
    from app.agents.memory import MemoryAgent
    from app.services.llm import LLMService

    llm = AsyncMock(spec=LLMService)
    llm.complete.return_value = json.dumps({"tags": ["system design trade-offs", "time complexity analysis"]})
    agent = MemoryAgent(llm=llm)
    scorecard = ScorecardResult(
        overall_score=7,
        strengths=["clarity"],
        areas_to_improve=["weak depth"],
        recommendation="hire",
    )

    tags = await agent.extract_weaknesses(scorecard)
    assert tags == ["system design trade-offs", "time complexity analysis"]


def test_create_from_jd_passes_existing_weaknesses_to_pipeline(client):
    with patch("app.routes.sessions.orchestrator") as mock_orch, \
         patch("app.services.llm.LLMService.complete", new=AsyncMock(return_value="Hello")), \
         patch("app.routes.sessions.MemoryAgent.extract_weaknesses", new=AsyncMock(return_value=["time complexity analysis", "behavioral STAR format"])):
        mock_orch.run_jd_pipeline = AsyncMock(return_value=_pipeline_result())
        first_session = client.post("/api/sessions/from-jd", json={"jd": "Initial JD"}).json()["session_id"]
        mock_orch.run_scoring = AsyncMock(
            return_value=ScorecardResult(
                overall_score=7,
                strengths=["clarity"],
                areas_to_improve=["depth"],
                recommendation="hire",
            )
        )
        client.post(f"/api/sessions/{first_session}/finish")

    with patch("app.routes.sessions.orchestrator") as mock_orch, \
         patch("app.services.llm.LLMService.complete", new=AsyncMock(return_value="Hello")):
        mock_orch.run_jd_pipeline = AsyncMock(return_value=_pipeline_result())
        resp = client.post("/api/sessions/from-jd", json={"jd": "Stripe hiring."})

    assert resp.status_code == 200
    kwargs = mock_orch.run_jd_pipeline.await_args.kwargs
    assert "user_weaknesses" in kwargs
    assert "time complexity analysis" in kwargs["user_weaknesses"]


def test_finishing_two_sessions_increments_frequency(client):
    with patch("app.routes.sessions.orchestrator") as mock_orch, \
         patch("app.services.llm.LLMService.complete", new=AsyncMock(return_value="Hello")):
        mock_orch.run_jd_pipeline = AsyncMock(return_value=_pipeline_result())
        s1 = client.post("/api/sessions/from-jd", json={"jd": "JD one"}).json()["session_id"]
        s2 = client.post("/api/sessions/from-jd", json={"jd": "JD two"}).json()["session_id"]

    with patch("app.routes.sessions.orchestrator") as mock_orch, \
         patch("app.routes.sessions.MemoryAgent.extract_weaknesses", new=AsyncMock(return_value=["time complexity analysis"])):
        mock_orch.run_scoring = AsyncMock(
            return_value=ScorecardResult(
                overall_score=7,
                strengths=["clarity"],
                areas_to_improve=["depth"],
                recommendation="hire",
            )
        )
        client.post(f"/api/sessions/{s1}/finish")
        client.post(f"/api/sessions/{s2}/finish")

    memory = client.get("/api/sessions/memory").json()
    tag = next(m for m in memory if m["area"] == "time complexity analysis")
    assert tag["frequency"] >= 2

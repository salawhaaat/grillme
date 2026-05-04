from unittest.mock import AsyncMock, patch

from app.agents.schemas import (
    AxisScore,
    CodingProblem,
    InterviewPipelineResult,
    ParsedJD,
    PersonaVoice,
    ScorecardAxes,
    ScorecardV2,
)


def _problem() -> CodingProblem:
    return CodingProblem(
        title="Two Sum",
        difficulty="Easy",
        problem_statement="Find two indices whose values sum to target.",
        full_problem="Given nums and target, return indices.",
        starter_code=(
            "class Solution:\n"
            "    def twoSum(self, nums: list[int], target: int) -> list[int]:\n"
            "        pass\n"
        ),
        test_cases=[{"input": [[2, 7, 11, 15], 9], "expected": [0, 1]}],
        method_name="twoSum",
    )


def _voice() -> PersonaVoice:
    return PersonaVoice(persona_text="You are Alex, concise and rigorous.", oa_platform="LeetCode")


def _parsed() -> ParsedJD:
    return ParsedJD(
        company="Stripe",
        role="Backend Engineer",
        level="senior",
        key_skills=["Python"],
        focus_areas=["algorithms"],
    )


def _raw_problem() -> dict:
    return {
        "title": "Two Sum",
        "difficulty": "Easy",
        "description": "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.",
    }


def _pipeline_result(*, parsed: ParsedJD | None = None) -> InterviewPipelineResult:
    return InterviewPipelineResult(
        parsed_jd=parsed,
        problem=None,
        raw_problem=_raw_problem(),
        persona=_voice(),
        research=None,
    )


def _scorecard_v2() -> ScorecardV2:
    return ScorecardV2(
        overall_score=7,
        axes=ScorecardAxes(
            technical_correctness=AxisScore(score=8, comment="Correct"),
            process_of_thought=AxisScore(score=7, comment="Reasoned"),
            curiosity=AxisScore(score=6, comment="Some questions"),
            self_presentation=AxisScore(score=7, comment="Clear"),
            closing_questions=AxisScore(score=6, comment="Adequate"),
            code_quality=AxisScore(score=8, comment="Clean"),
        ),
        strengths=["clarity"],
        areas_to_improve=["depth"],
        recommendation="hire",
    )


def test_create_session_text_success(client):
    async def fake_complete(*_, **__):
        return "Here's your problem."

    with patch("app.routes.sessions.orchestrator") as mock_orch, \
         patch("app.services.llm.LLMService.complete", new=fake_complete), \
         patch("app.routes.sessions._process_problem_background"):
        mock_orch.run_interview_pipeline = AsyncMock(return_value=_pipeline_result(parsed=None))
        resp = client.post(
            "/api/sessions/create",
            json={"source": "text", "content": "Build a hash-map solution", "difficulty": "medium"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert data["problem"]["title"] == "Two Sum"
    assert data["problem_ready"] is False   # problem not ready yet — background task pending
    assert data["starter_code"] is None     # not ready yet
    assert data["opening_message"] == "Here's your problem."


def test_create_session_jd_includes_parsed_fields(client):
    async def fake_complete(*_, **__):
        return "Let's start."

    from app.agents.schemas import PersonaOutput, QuestionBank, CodingRound, PipelineResult
    jd_result = PipelineResult(
        parsed_jd=_parsed(),
        persona=PersonaOutput(
            persona_text="You are Elon.",
            question_bank=QuestionBank(
                warmup=["Tell me about yourself"],
                trivia=["What is O(n)?", "Explain recursion", "What is a hash map?", "What is a stack?"],
                culture_fit=["Describe a challenge"],
                coding=CodingRound(type="leetcode", topic="Two Sum", hints=[]),
            ),
            prep_plan="Study algorithms.",
            oa_platform=None,
        ),
    )

    with patch("app.routes.sessions.orchestrator") as mock_orch, \
         patch("app.services.llm.LLMService.complete", new=fake_complete), \
         patch("app.routes.sessions._process_problem_background"):
        mock_orch.run_interview_pipeline = AsyncMock(return_value=_pipeline_result(parsed=_parsed()))
        mock_orch.run_jd_pipeline = AsyncMock(return_value=jd_result)
        resp = client.post(
            "/api/sessions/create",
            json={"source": "jd", "content": "Stripe JD text", "difficulty": "well_done"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["company"] == "Stripe"
    assert data["role"] == "Backend Engineer"
    assert data["level"] == "senior"


def test_create_session_url_success(client):
    async def fake_complete(*_, **__):
        return "Begin."

    with patch("app.routes.sessions.orchestrator") as mock_orch, \
         patch("app.services.llm.LLMService.complete", new=fake_complete), \
         patch("app.routes.sessions._process_problem_background"):
        mock_orch.run_interview_pipeline = AsyncMock(return_value=_pipeline_result(parsed=None))
        resp = client.post(
            "/api/sessions/create",
            json={"source": "url", "content": "https://leetcode.com/problems/two-sum/", "difficulty": "rare"},
        )

    assert resp.status_code == 200
    assert resp.json()["source"] == "url"


def test_create_session_empty_content_422(client):
    resp = client.post(
        "/api/sessions/create",
        json={"source": "text", "content": "   ", "difficulty": "medium"},
    )
    assert resp.status_code == 422


def test_create_session_pipeline_failure_503(client):
    with patch("app.routes.sessions.orchestrator") as mock_orch:
        mock_orch.run_interview_pipeline = AsyncMock(side_effect=RuntimeError("boom"))
        resp = client.post(
            "/api/sessions/create",
            json={"source": "text", "content": "problem text", "difficulty": "medium"},
        )

    assert resp.status_code == 503
    assert "Pipeline failed" in resp.json()["detail"]


def test_get_session_returns_problem_fields_for_new_session(client):
    async def fake_complete(*_, **__):
        return "Here's your problem."

    with patch("app.routes.sessions.orchestrator") as mock_orch, \
         patch("app.services.llm.LLMService.complete", new=fake_complete), \
         patch("app.routes.sessions._process_problem_background"):
        mock_orch.run_interview_pipeline = AsyncMock(return_value=_pipeline_result(parsed=None))
        create_resp = client.post(
            "/api/sessions/create",
            json={"source": "text", "content": "problem text", "difficulty": "medium"},
        )

    sid = create_resp.json()["session_id"]
    resp = client.get(f"/api/sessions/{sid}")

    assert resp.status_code == 200
    data = resp.json()
    # Problem fields are null until background task completes
    assert data["problem_statement"] is None
    assert data["starter_code"] is None


def test_finish_session_new_session_returns_six_axis_scorecard_shape(client):
    async def fake_complete(*_, **__):
        return "Let's begin."

    with patch("app.routes.sessions.orchestrator") as mock_orch, \
         patch("app.services.llm.LLMService.complete", new=fake_complete), \
         patch("app.routes.sessions._process_problem_background"):
        mock_orch.run_interview_pipeline = AsyncMock(return_value=_pipeline_result(parsed=None))
        create_resp = client.post(
            "/api/sessions/create",
            json={"source": "text", "content": "problem text", "difficulty": "medium"},
        )

    sid = create_resp.json()["session_id"]
    with patch("app.routes.sessions.orchestrator") as mock_orch:
        mock_orch.run_six_axis_scoring = AsyncMock(return_value=_scorecard_v2())
        finish_resp = client.post(f"/api/sessions/{sid}/finish")

    assert finish_resp.status_code == 200
    scorecard = finish_resp.json()["scorecard"]
    assert "axes" in scorecard
    assert "technical_correctness" in scorecard["axes"]
    assert "curiosity" in scorecard["axes"]

from unittest.mock import AsyncMock

from app.agents.orchestrator import Orchestrator
from app.agents.schemas import (
    AxisScore,
    CodingProblem,
    InterviewPipelineResult,
    ParsedJD,
    PersonaVoice,
    ResearchIntel,
    ScorecardAxes,
    ScorecardV2,
)
from app.services.llm import LLMService


def _parsed() -> ParsedJD:
    return ParsedJD(
        company="Stripe",
        role="Senior Software Engineer",
        level="senior",
        key_skills=["Python"],
        focus_areas=["system design"],
    )


def _problem() -> CodingProblem:
    return CodingProblem(
        title="Two Sum",
        difficulty="Easy",
        problem_statement="Find two indices whose values sum to target.",
        full_problem="Given nums and target, return two indices.",
        starter_code=(
            "class Solution:\n"
            "    def twoSum(self, nums: list[int], target: int) -> list[int]:\n"
            "        pass\n"
        ),
        test_cases=[{"input": [[2, 7, 11, 15], 9], "expected": [0, 1]}],
        method_name="twoSum",
    )


def _voice() -> PersonaVoice:
    return PersonaVoice(persona_text="You are Alex", oa_platform="LeetCode")


def _scorecard_v2() -> ScorecardV2:
    return ScorecardV2(
        overall_score=7,
        axes=ScorecardAxes(
            technical_correctness=AxisScore(score=8, comment="Good"),
            process_of_thought=AxisScore(score=7, comment="Clear"),
            curiosity=AxisScore(score=6, comment="Asked questions"),
            self_presentation=AxisScore(score=7, comment="Professional"),
            closing_questions=AxisScore(score=6, comment="Somewhat specific"),
            code_quality=AxisScore(score=8, comment="Readable"),
        ),
        strengths=["clarity"],
        areas_to_improve=["depth"],
        recommendation="hire",
    )


async def test_run_interview_pipeline_jd_returns_full_result():
    llm = AsyncMock(spec=LLMService)
    research = AsyncMock()
    research.search = AsyncMock(return_value={"culture_notes": "High bar", "no_results": False})
    orch = Orchestrator(llm=llm, research=research)
    orch.parser.run = AsyncMock(return_value=_parsed())
    raw = {"title": "Two Sum", "difficulty": "Easy", "description": "Find two indices."}
    orch.problem_agent.fetch_raw = AsyncMock(return_value=raw)

    result = await orch.run_interview_pipeline(source="jd", content="jd text")

    assert isinstance(result, InterviewPipelineResult)
    assert result.parsed_jd is not None
    assert result.raw_problem["title"] == "Two Sum"
    assert result.problem is None  # filled by background task
    assert "Elon" in result.persona.persona_text


async def test_run_interview_pipeline_url_has_no_parsed_jd():
    llm = AsyncMock(spec=LLMService)
    orch = Orchestrator(llm=llm)
    raw = {"title": "Two Sum", "difficulty": "Easy", "description": "Find two indices."}
    orch.problem_agent.fetch_raw = AsyncMock(return_value=raw)

    result = await orch.run_interview_pipeline(
        source="url",
        content="https://leetcode.com/problems/two-sum/",
    )

    assert result.parsed_jd is None
    assert result.raw_problem["title"] == "Two Sum"
    assert result.problem is None


async def test_run_interview_pipeline_text_has_no_parsed_jd_or_research():
    llm = AsyncMock(spec=LLMService)
    orch = Orchestrator(llm=llm)
    raw = {"title": "Two Sum", "difficulty": "Easy", "description": "Find two indices."}
    orch.problem_agent.fetch_raw = AsyncMock(return_value=raw)

    result = await orch.run_interview_pipeline(source="text", content="problem statement")

    assert result.parsed_jd is None
    assert result.research is None


async def test_run_interview_pipeline_passes_user_weaknesses_to_problem_agent():
    """User weaknesses are passed to the problem agent for problem selection weighting."""
    llm = AsyncMock(spec=LLMService)
    orch = Orchestrator(llm=llm)
    raw = {"title": "Two Sum", "difficulty": "Easy", "description": "Find two indices."}
    orch.problem_agent.fetch_raw = AsyncMock(return_value=raw)

    await orch.run_interview_pipeline(
        source="text",
        content="problem statement",
        user_weaknesses=["complexity analysis"],
    )

    problem_input = orch.problem_agent.fetch_raw.await_args.args[0]
    assert problem_input.user_weaknesses == ["complexity analysis"]


async def test_run_six_axis_scoring_returns_scorecard_v2():
    llm = AsyncMock(spec=LLMService)
    orch = Orchestrator(llm=llm)
    orch.scorer.score_six_axes = AsyncMock(return_value=_scorecard_v2())

    result = await orch.run_six_axis_scoring(
        messages=[{"role": "user", "content": "Can I clarify constraints?"}],
        persona="You are Alex",
        problem=_problem(),
    )

    assert isinstance(result, ScorecardV2)
    assert result.overall_score == 7

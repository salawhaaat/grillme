import json
from unittest.mock import AsyncMock

from app.agents.scorer import ScorerAgent
from app.agents.schemas import CodingProblem, ScorecardV2
from app.services.llm import LLMService


def _problem() -> CodingProblem:
    return CodingProblem(
        title="Two Sum",
        difficulty="Easy",
        problem_statement="Find two indices whose values sum to target.",
        full_problem="Given nums and target, return two indices.",
        starter_code="class Solution:\n    def twoSum(self, nums: list[int], target: int) -> list[int]:\n        pass\n",
        test_cases=[{"input": [[2, 7, 11, 15], 9], "expected": [0, 1]}],
        method_name="twoSum",
    )


def _scorecard_json(*, curiosity: int, closing: int) -> str:
    return json.dumps(
        {
            "overall_score": 0,
            "axes": {
                "technical_correctness": {"score": 8, "comment": "Correct core approach."},
                "process_of_thought": {"score": 7, "comment": "Reasoning was mostly clear."},
                "curiosity": {"score": curiosity, "comment": "Asked some clarifying questions."},
                "self_presentation": {"score": 7, "comment": "Communicated clearly."},
                "closing_questions": {"score": closing, "comment": "Asked role-relevant closing questions."},
                "code_quality": {"score": 8, "comment": "Readable and structured code."},
            },
            "strengths": ["Reasoning clarity"],
            "areas_to_improve": ["Ask earlier clarifying questions"],
            "recommendation": "hire",
        }
    )


async def test_score_six_axes_returns_scorecard_v2_with_all_axes():
    llm = AsyncMock(spec=LLMService)
    llm.complete.side_effect = [_scorecard_json(curiosity=6, closing=6), _scorecard_json(curiosity=6, closing=6)]
    agent = ScorerAgent(llm=llm)

    result = await agent.score_six_axes(
        messages=[{"role": "user", "content": "Can I clarify input constraints?"}],
        persona="You are an interviewer.",
        problem=_problem(),
    )

    assert isinstance(result, ScorecardV2)
    assert result.axes.technical_correctness.score == 8
    assert result.axes.process_of_thought.score == 7
    assert result.axes.curiosity.score == 6
    assert result.axes.self_presentation.score == 7
    assert result.axes.closing_questions.score == 6
    assert result.axes.code_quality.score == 8


async def test_score_six_axes_includes_clarification_penalty_in_draft_prompt():
    llm = AsyncMock(spec=LLMService)
    llm.complete.side_effect = [_scorecard_json(curiosity=8, closing=5), _scorecard_json(curiosity=4, closing=5)]
    agent = ScorerAgent(llm=llm)

    await agent.score_six_axes(
        messages=[{"role": "user", "content": "class Solution:\n    def solve(self):\n        pass"}],
        persona="You are an interviewer.",
    )

    draft_system_prompt = llm.complete.call_args_list[0].args[0][0]["content"]
    assert "cap `curiosity.score` at 4" in draft_system_prompt


async def test_score_six_axes_closing_questions_can_score_above_six():
    llm = AsyncMock(spec=LLMService)
    llm.complete.side_effect = [_scorecard_json(curiosity=6, closing=8), _scorecard_json(curiosity=6, closing=8)]
    agent = ScorerAgent(llm=llm)

    result = await agent.score_six_axes(
        messages=[
            {"role": "assistant", "content": "Any final questions?"},
            {
                "role": "user",
                "content": (
                    "How does this team balance delivery speed with reliability goals, "
                    "and what code quality signals matter most in your reviews?"
                ),
            },
        ],
        persona="You are an interviewer.",
    )

    assert result.axes.closing_questions.score > 6


async def test_score_six_axes_computes_weighted_overall_score():
    llm = AsyncMock(spec=LLMService)
    llm.complete.side_effect = [_scorecard_json(curiosity=6, closing=8), _scorecard_json(curiosity=6, closing=8)]
    agent = ScorerAgent(llm=llm)

    result = await agent.score_six_axes(
        messages=[{"role": "user", "content": "Can I clarify expected output ordering?"}],
        persona="You are an interviewer.",
    )

    expected = round(8 * 0.25 + 7 * 0.20 + 6 * 0.15 + 7 * 0.15 + 8 * 0.10 + 8 * 0.15)
    assert result.overall_score == expected

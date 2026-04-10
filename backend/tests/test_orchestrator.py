from unittest.mock import AsyncMock, patch

from app.agents.orchestrator import Orchestrator
from app.agents.schemas import (
    CodingRound,
    ParsedJD,
    PersonaOutput,
    PipelineResult,
    ResearchIntel,
    ScorecardResult,
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


def _persona_output() -> PersonaOutput:
    return PersonaOutput(
        persona_text="You are Alex",
        question_bank={
            "warmup": ["Tell me about yourself"],
            "trivia": ["Explain CAP theorem"],
            "culture_fit": ["Describe a conflict"],
            "coding": CodingRound(type="system_design", topic="Design payments", hints=["idempotency"]),
        },
        prep_plan="1. Practice design",
        oa_platform=None,
    )


async def test_run_jd_pipeline_returns_pipeline_result():
    llm = AsyncMock(spec=LLMService)
    orch = Orchestrator(llm=llm)
    orch.parser.run = AsyncMock(return_value=_parsed())
    orch.persona.run = AsyncMock(return_value=_persona_output())

    result = await orch.run_jd_pipeline("jd text")

    assert isinstance(result, PipelineResult)
    assert result.parsed_jd.company == "Stripe"


async def test_run_jd_pipeline_without_research_still_works():
    llm = AsyncMock(spec=LLMService)
    orch = Orchestrator(llm=llm, research=None)
    orch.parser.run = AsyncMock(return_value=_parsed())
    orch.persona.run = AsyncMock(return_value=_persona_output())

    result = await orch.run_jd_pipeline("jd text")

    assert result.research is None
    assert result.persona.persona_text == "You are Alex"


async def test_run_jd_pipeline_research_failure_is_graceful():
    llm = AsyncMock(spec=LLMService)
    research = AsyncMock()
    research.search = AsyncMock(side_effect=RuntimeError("boom"))
    orch = Orchestrator(llm=llm, research=research)
    orch.parser.run = AsyncMock(return_value=_parsed())
    orch.persona.run = AsyncMock(return_value=_persona_output())

    result = await orch.run_jd_pipeline("jd text")

    assert result.research is None
    orch.persona.run.assert_awaited_once()


async def test_run_jd_pipeline_passes_user_weaknesses_to_persona():
    llm = AsyncMock(spec=LLMService)
    orch = Orchestrator(llm=llm, research=None)
    orch.parser.run = AsyncMock(return_value=_parsed())
    orch.persona.run = AsyncMock(return_value=_persona_output())

    await orch.run_jd_pipeline("jd text", user_weaknesses=["system design"])

    persona_input = orch.persona.run.await_args.args[0]
    assert persona_input.user_weaknesses == ["system design"]


async def test_run_scoring_returns_scorecard_result():
    llm = AsyncMock(spec=LLMService)
    orch = Orchestrator(llm=llm)
    orch.scorer.run = AsyncMock(
        return_value=ScorecardResult(
            overall_score=8,
            strengths=["clarity"],
            areas_to_improve=["depth"],
            recommendation="hire",
        )
    )

    result = await orch.run_scoring([{"role": "user", "content": "Hi"}], "persona")

    assert isinstance(result, ScorecardResult)
    assert result.overall_score == 8


async def test_build_problem_persona_returns_string():
    llm = AsyncMock(spec=LLMService)
    llm.complete = AsyncMock(return_value="You are Sam")
    orch = Orchestrator(llm=llm)

    result = await orch.build_problem_persona({"title": "Two Sum", "difficulty": "Easy"})

    assert isinstance(result, str)
    assert result == "You are Sam"

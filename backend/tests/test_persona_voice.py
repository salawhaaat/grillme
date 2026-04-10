from unittest.mock import AsyncMock

from app.agents.persona import PersonaAgent
from app.agents.schemas import CodingProblem, ParsedJD, PersonaVoice, PersonaVoiceInput, ResearchIntel
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


def _parsed_jd() -> ParsedJD:
    return ParsedJD(
        company="Stripe",
        role="Backend Engineer",
        level="senior",
        key_skills=["Python", "Algorithms"],
        focus_areas=["problem solving"],
    )


async def test_build_voice_with_parsed_jd_and_problem_returns_persona_voice():
    llm = AsyncMock(spec=LLMService)
    llm.complete.return_value = "Maya is direct, curious, and probes trade-offs."
    agent = PersonaAgent(llm=llm)

    result = await agent.build_voice(
        PersonaVoiceInput(parsed_jd=_parsed_jd(), problem=_problem())
    )

    assert isinstance(result, PersonaVoice)
    assert result.persona_text


async def test_build_voice_without_parsed_jd_still_works():
    llm = AsyncMock(spec=LLMService)
    llm.complete.return_value = "Alex is calm and focused on reasoning clarity."
    agent = PersonaAgent(llm=llm)

    result = await agent.build_voice(PersonaVoiceInput(problem=_problem()))

    assert isinstance(result, PersonaVoice)
    assert result.persona_text.startswith("Alex")
    assert result.oa_platform is None


async def test_build_voice_injects_user_weaknesses_into_prompt():
    llm = AsyncMock(spec=LLMService)
    llm.complete.return_value = "Jordan asks targeted follow-ups."
    agent = PersonaAgent(llm=llm)

    await agent.build_voice(
        PersonaVoiceInput(
            parsed_jd=_parsed_jd(),
            problem=_problem(),
            user_weaknesses=["complexity analysis", "edge cases"],
        )
    )

    prompt = llm.complete.call_args.args[0][1]["content"]
    assert "complexity analysis" in prompt
    assert "edge cases" in prompt


async def test_build_voice_injects_research_culture_notes():
    llm = AsyncMock(spec=LLMService)
    llm.complete.return_value = "Priya balances rigor and empathy."
    agent = PersonaAgent(llm=llm)

    await agent.build_voice(
        PersonaVoiceInput(
            parsed_jd=_parsed_jd(),
            problem=_problem(),
            research=ResearchIntel(culture_notes="Strong ownership culture"),
        )
    )

    prompt = llm.complete.call_args.args[0][1]["content"]
    assert "Strong ownership culture" in prompt

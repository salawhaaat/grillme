import json
from unittest.mock import AsyncMock, patch

from app.agents.parser import ParseAgent
from app.agents.persona import PersonaAgent
from app.agents.scorer import ScorerAgent
from app.agents.schemas import (
    ParseInput,
    ParsedJD,
    PersonaInput,
    ResearchIntel,
    ScorecardResult,
    ScorerInput,
)
from app.services.llm import LLMService


def _parsed_jd() -> ParsedJD:
    return ParsedJD(
        company="Stripe",
        role="Senior Software Engineer",
        level="senior",
        key_skills=["Python", "distributed systems"],
        focus_areas=["system design"],
    )


async def test_parse_agent_run_returns_parsed_jd_model():
    llm = AsyncMock(spec=LLMService)
    llm.complete.return_value = json.dumps(_parsed_jd().model_dump())
    agent = ParseAgent(llm=llm)

    result = await agent.run(ParseInput(jd_raw="Stripe hiring senior SWE"))

    assert isinstance(result, ParsedJD)
    assert result.company == "Stripe"


async def test_parse_agent_run_validates_parsed_jd_schema():
    llm = AsyncMock(spec=LLMService)
    llm.complete.return_value = json.dumps({
        "company": "Stripe",
        "role": "Senior Software Engineer",
        "level": "senior",
        "key_skills": ["Python"],
        "focus_areas": ["system design"],
    })
    agent = ParseAgent(llm=llm)

    result = await agent.run(ParseInput(jd_raw="Stripe hiring senior SWE"))

    assert result.level == "senior"
    assert "Python" in result.key_skills


async def test_persona_agent_run_returns_persona_output_model():
    llm = AsyncMock(spec=LLMService)
    llm.complete.side_effect = [
        "You are Alex, a Stripe interviewer.",
        json.dumps({
            "warmup": ["Tell me about yourself"],
            "trivia": ["Explain CAP theorem"],
            "culture_fit": ["Describe a conflict"],
            "coding": {"type": "system_design", "topic": "Design payments", "hints": ["idempotency"]},
        }),
        "1. Practice system design",
    ]
    agent = PersonaAgent(llm=llm)

    with patch("app.agents.persona.detect_oa_platform", return_value=None):
        result = await agent.run(PersonaInput(parsed_jd=_parsed_jd()))

    assert result.persona_text.startswith("You are Alex")
    assert result.question_bank.coding.type == "system_design"


async def test_persona_agent_run_makes_three_llm_calls():
    llm = AsyncMock(spec=LLMService)
    llm.complete.side_effect = [
        "Persona",
        json.dumps({
            "warmup": ["a"],
            "trivia": ["b"],
            "culture_fit": ["c"],
            "coding": {"type": "leetcode", "topic": "Two Sum", "hints": ["hash map"]},
        }),
        "Prep",
    ]
    agent = PersonaAgent(llm=llm)

    with patch("app.agents.persona.detect_oa_platform", return_value=None):
        await agent.run(PersonaInput(parsed_jd=_parsed_jd()))

    assert llm.complete.await_count == 3


async def test_persona_agent_injects_research_into_persona_prompt():
    llm = AsyncMock(spec=LLMService)
    llm.complete.side_effect = [
        "Persona",
        json.dumps({
            "warmup": ["a"],
            "trivia": ["b"],
            "culture_fit": ["c"],
            "coding": {"type": "leetcode", "topic": "Two Sum", "hints": ["hash map"]},
        }),
        "Prep",
    ]
    agent = PersonaAgent(llm=llm)
    research = ResearchIntel(
        culture_notes="Collaborative bar-raiser interviews",
        common_questions=["System design deep dive"],
    )

    with patch("app.agents.persona.detect_oa_platform", return_value=None):
        await agent.run(PersonaInput(parsed_jd=_parsed_jd(), research=research))

    calls = llm.complete.call_args_list
    persona_user_content = calls[0].args[0][1]["content"]
    assert "Real interview reports suggest" in persona_user_content
    assert "Collaborative bar-raiser interviews" in persona_user_content


async def test_persona_agent_injects_weaknesses_into_prep_plan_prompt():
    llm = AsyncMock(spec=LLMService)
    llm.complete.side_effect = [
        "Persona",
        json.dumps({
            "warmup": ["a"],
            "trivia": ["b"],
            "culture_fit": ["c"],
            "coding": {"type": "leetcode", "topic": "Two Sum", "hints": ["hash map"]},
        }),
        "Prep",
    ]
    agent = PersonaAgent(llm=llm)

    with patch("app.agents.persona.detect_oa_platform", return_value=None):
        await agent.run(PersonaInput(parsed_jd=_parsed_jd(), user_weaknesses=["system design", "complexity analysis"]))

    calls = llm.complete.call_args_list
    prep_user_content = calls[2].args[0][1]["content"]
    assert "previously struggled with" in prep_user_content
    assert "system design" in prep_user_content


async def test_scorer_agent_run_returns_scorecard_result_model():
    llm = AsyncMock(spec=LLMService)
    llm.complete.side_effect = [
        json.dumps({
            "overall_score": 7,
            "strengths": ["clarity"],
            "areas_to_improve": ["depth"],
            "recommendation": "hire",
        }),
        json.dumps({
            "overall_score": 8,
            "strengths": ["clarity"],
            "areas_to_improve": ["depth"],
            "recommendation": "hire",
        }),
    ]
    agent = ScorerAgent(llm=llm)
    input_data = ScorerInput(
        messages=[{"role": "user", "content": "Hello"}],
        persona="You are Alex",
    )

    result = await agent.run(input_data)

    assert isinstance(result, ScorecardResult)
    assert result.overall_score == 8


async def test_scorer_agent_makes_two_llm_calls():
    llm = AsyncMock(spec=LLMService)
    llm.complete.side_effect = [
        json.dumps({
            "overall_score": 7,
            "strengths": ["clarity"],
            "areas_to_improve": ["depth"],
            "recommendation": "hire",
        }),
        json.dumps({
            "overall_score": 8,
            "strengths": ["clarity"],
            "areas_to_improve": ["depth"],
            "recommendation": "hire",
        }),
    ]
    agent = ScorerAgent(llm=llm)

    await agent.run(
        ScorerInput(messages=[{"role": "user", "content": "Hello"}], persona="You are Alex")
    )

    assert llm.complete.await_count == 2


async def test_scorer_agent_prompt_mentions_thought_process_and_closing_questions():
    llm = AsyncMock(spec=LLMService)
    llm.complete.side_effect = [
        json.dumps({
            "overall_score": 7,
            "strengths": ["clarity"],
            "areas_to_improve": ["depth"],
            "recommendation": "hire",
        }),
        json.dumps({
            "overall_score": 8,
            "strengths": ["clarity"],
            "areas_to_improve": ["depth"],
            "recommendation": "hire",
        }),
    ]
    agent = ScorerAgent(llm=llm)

    await agent.run(
        ScorerInput(messages=[{"role": "user", "content": "Hello"}], persona="You are Alex")
    )

    first_system_prompt = llm.complete.call_args_list[0].args[0][0]["content"].lower()
    assert "thought process" in first_system_prompt
    assert "closing-stage interview behavior" in first_system_prompt

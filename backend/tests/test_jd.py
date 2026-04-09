import json
import pytest
from unittest.mock import AsyncMock

from app.services.jd import JDService
from app.services.llm import LLMService

JD_TEXT = "Stripe is hiring a Senior Software Engineer to build payment infrastructure."

PARSED_JD = {
    "company": "Stripe",
    "role": "Senior Software Engineer",
    "level": "senior",
    "key_skills": ["Python", "distributed systems"],
    "focus_areas": ["system design", "algorithms"],
}


@pytest.fixture
def mock_llm():
    return AsyncMock(spec=LLMService)


@pytest.fixture
def jd_service(mock_llm):
    return JDService(llm=mock_llm)


async def test_parse_jd_returns_structured_dict(jd_service, mock_llm):
    mock_llm.complete.return_value = json.dumps(PARSED_JD)

    result = await jd_service.parse_jd(JD_TEXT)

    assert result["company"] == "Stripe"
    assert result["role"] == "Senior Software Engineer"
    assert "Python" in result["key_skills"]
    mock_llm.complete.assert_called_once()
    _, kwargs = mock_llm.complete.call_args
    assert kwargs.get("json_mode") is True


async def test_build_persona_returns_string(jd_service, mock_llm):
    mock_llm.complete.return_value = "You are Alex, a senior Stripe engineer."

    result = await jd_service.build_persona(PARSED_JD)

    assert isinstance(result, str)
    assert len(result) > 0
    mock_llm.complete.assert_called_once()


async def test_generate_prep_plan_returns_string(jd_service, mock_llm):
    mock_llm.complete.return_value = "1. Study system design\n2. Practice algorithms"

    result = await jd_service.generate_prep_plan(PARSED_JD)

    assert isinstance(result, str)
    assert len(result) > 0
    mock_llm.complete.assert_called_once()



async def test_generate_question_bank_returns_structured_dict(jd_service, mock_llm):
    bank = {
        "warmup": ["Tell me about yourself", "Why NVIDIA?"],
        "trivia": ["What is a kernel panic?", "How does Kubernetes scheduler work?"],
        "culture_fit": ["Describe a time you debugged a hard production issue"],
        "coding": {
            "type": "system_design",
            "topic": "Design a CI/CD pipeline for GPU workloads",
            "hints": ["Consider containerization", "Think about artifact caching"],
        },
    }
    mock_llm.complete.return_value = json.dumps(bank)

    result = await jd_service.generate_question_bank(PARSED_JD)

    assert "warmup" in result
    assert "trivia" in result
    assert "culture_fit" in result
    assert "coding" in result
    assert result["coding"]["type"] in ("leetcode", "system_design")
    assert isinstance(result["trivia"], list)
    _, kwargs = mock_llm.complete.call_args
    assert kwargs.get("json_mode") is True


async def test_process_jd_chains_three_steps(jd_service, mock_llm):
    bank = {"warmup": ["Tell me about yourself"], "trivia": ["What is a kernel panic?"],
            "culture_fit": ["Tell me about a hard bug"], "coding": {"type": "system_design",
            "topic": "Design CI/CD", "hints": []}}
    mock_llm.complete.side_effect = [
        json.dumps(PARSED_JD),
        "You are Alex, a Stripe engineer.",
        json.dumps(bank),
    ]

    parsed, persona, question_bank = await jd_service.process_jd(JD_TEXT)

    assert parsed["company"] == "Stripe"
    assert "Alex" in persona
    assert "warmup" in question_bank
    assert mock_llm.complete.call_count == 3


async def test_generate_scorecard_returns_json_string(jd_service, mock_llm):
    scorecard = {"overall_score": 8, "strengths": ["clear thinking"], "recommendation": "hire"}
    mock_llm.complete.return_value = json.dumps(scorecard)
    messages = [
        {"role": "user", "content": "Tell me about yourself"},
        {"role": "assistant", "content": "I have 5 years of Python experience."},
    ]

    result = await jd_service.generate_scorecard(messages, "You are Alex from Stripe.")

    assert isinstance(result, str)
    parsed = json.loads(result)
    assert "overall_score" in parsed
    _, kwargs = mock_llm.complete.call_args
    assert kwargs.get("json_mode") is True

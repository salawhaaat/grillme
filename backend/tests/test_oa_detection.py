from unittest.mock import AsyncMock, patch

from app.agents.schemas import CodingRound, ParsedJD, PersonaOutput, PipelineResult, QuestionBank
from app.services.jd import detect_oa_platform


def test_detect_oa_platform_hackerrank_match():
    jd = "Our process includes an online coding round on HackerRank."
    assert detect_oa_platform(jd) == "HackerRank"


def test_detect_oa_platform_codesignal_case_insensitive():
    jd = "You will complete a timed codesignal challenge."
    assert detect_oa_platform(jd) == "CodeSignal"


def test_detect_oa_platform_no_match_returns_none():
    jd = "We use a take-home assignment and a final panel."
    assert detect_oa_platform(jd) is None


def test_detect_oa_platform_multiple_returns_first_match_in_text():
    jd = "Candidates complete a Codility test before a HackerRank follow-up."
    assert detect_oa_platform(jd) == "Codility"


def test_create_from_jd_response_includes_oa_platform(client):
    parsed = {
        "company": "Stripe",
        "role": "Senior Software Engineer",
        "level": "senior",
        "key_skills": ["Python"],
        "focus_areas": ["algorithms"],
    }
    persona = "You are Alex, a Stripe interviewer."
    question_bank = {
        "warmup": ["Tell me about yourself"],
        "trivia": ["Explain CAP theorem"],
        "culture_fit": ["Tell me about a conflict"],
        "coding": {"type": "leetcode", "topic": "Two Sum", "hints": []},
    }
    prep_plan = "1. Practice arrays\n2. Practice hash maps"

    async def fake_complete(*_, **__):
        return "Hi, I'm Alex. Let's start."

    with patch("app.routes.sessions.orchestrator") as mock_orch, \
         patch("app.services.llm.LLMService.complete", new=fake_complete):
        mock_orch.run_jd_pipeline = AsyncMock(
            return_value=PipelineResult(
                parsed_jd=ParsedJD(**parsed),
                persona=PersonaOutput(
                    persona_text=persona,
                    question_bank=QuestionBank(
                        warmup=question_bank["warmup"],
                        trivia=question_bank["trivia"],
                        culture_fit=question_bank["culture_fit"],
                        coding=CodingRound(**question_bank["coding"]),
                    ),
                    prep_plan=prep_plan,
                    oa_platform="HackerRank",
                ),
            )
        )
        resp = client.post(
            "/api/sessions/from-jd",
            json={"jd": "The process includes a HackerRank OA."},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["oa_platform"] == "HackerRank"

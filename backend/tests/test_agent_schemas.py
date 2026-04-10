import pytest
from pydantic import ValidationError

from app.agents.schemas import (
    CodingRound,
    ParsedJD,
    PersonaInput,
    QuestionBank,
    ResearchIntel,
    ScorecardResult,
    UserWeakness,
)


def test_parsed_jd_validates_with_correct_data():
    parsed = ParsedJD(
        company="Stripe",
        role="Backend Engineer",
        level="senior",
        key_skills=["Python", "SQL"],
        focus_areas=["system design"],
    )
    assert parsed.company == "Stripe"
    assert parsed.level == "senior"


def test_parsed_jd_rejects_missing_required_fields():
    with pytest.raises(ValidationError):
        ParsedJD(
            company="Stripe",
            role="Backend Engineer",
            level="senior",
            key_skills=["Python"],
        )


def test_research_intel_defaults():
    intel = ResearchIntel()
    assert intel.common_questions == []
    assert intel.tips == []
    assert intel.no_results is False


def test_persona_input_accepts_optional_research_none():
    parsed = ParsedJD(
        company="Stripe",
        role="Backend Engineer",
        level="senior",
        key_skills=["Python"],
        focus_areas=["system design"],
    )
    persona_input = PersonaInput(parsed_jd=parsed, research=None)
    assert persona_input.research is None


def test_scorecard_result_validates_complete_scorecard():
    scorecard = ScorecardResult(
        overall_score=8,
        strengths=["clarity"],
        areas_to_improve=["depth"],
        recommendation="hire",
    )
    assert scorecard.overall_score == 8
    assert scorecard.recommendation == "hire"


def test_question_bank_contains_coding_sub_model():
    bank = QuestionBank(
        warmup=["Tell me about yourself"],
        trivia=["Explain CAP theorem"],
        culture_fit=["Describe a conflict"],
        coding=CodingRound(type="system_design", topic="Design payments", hints=["idempotency"]),
    )
    assert isinstance(bank.coding, CodingRound)
    assert bank.coding.type == "system_design"


def test_user_weakness_defaults_frequency_to_one():
    weakness = UserWeakness(area="system design", last_seen="2026-04-10")
    assert weakness.frequency == 1

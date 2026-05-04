from typing import Literal

from pydantic import BaseModel, Field


class ParseInput(BaseModel):
    jd_raw: str


class ParsedJD(BaseModel):
    company: str
    role: str
    level: str
    key_skills: list[str]
    focus_areas: list[str]


class ResearchInput(BaseModel):
    company: str
    role: str


class ResearchIntel(BaseModel):
    common_questions: list[str] = Field(default_factory=list)
    culture_notes: str = ""
    interview_format: str = ""
    tips: list[str] = Field(default_factory=list)
    no_results: bool = False


class CodingRound(BaseModel):
    type: str
    topic: str
    hints: list[str]


class QuestionBank(BaseModel):
    warmup: list[str]
    trivia: list[str]
    culture_fit: list[str]
    coding: CodingRound


class PersonaInput(BaseModel):
    parsed_jd: ParsedJD
    research: ResearchIntel | None = None
    user_weaknesses: list[str] = Field(default_factory=list)
    cv_text: str | None = None


class PersonaOutput(BaseModel):
    persona_text: str
    question_bank: QuestionBank
    prep_plan: str
    oa_platform: str | None = None


class PipelineResult(BaseModel):
    parsed_jd: ParsedJD
    persona: PersonaOutput
    research: ResearchIntel | None = None


class ScorerInput(BaseModel):
    messages: list[dict]
    persona: str


class ScorecardResult(BaseModel):
    overall_score: int
    strengths: list[str]
    areas_to_improve: list[str]
    recommendation: str


class UserWeakness(BaseModel):
    area: str
    frequency: int = 1
    last_seen: str


class TestCase(BaseModel):
    input: list = Field(default_factory=list)
    expected: object


class CodingProblem(BaseModel):
    title: str
    difficulty: str
    problem_statement: str
    full_problem: str
    starter_code: str
    test_cases: list[dict]
    method_name: str


class ProblemInput(BaseModel):
    source: Literal["jd", "url", "text"]
    content: str
    parsed_jd: ParsedJD | None = None
    user_weaknesses: list[str] = Field(default_factory=list)


class CreateSessionInput(BaseModel):
    source: Literal["jd", "url", "text"]
    content: str
    difficulty: Literal["rare", "medium", "well_done"] = "medium"


class PersonaVoice(BaseModel):
    persona_text: str
    oa_platform: str | None = None


class PersonaVoiceInput(BaseModel):
    parsed_jd: ParsedJD | None = None
    problem: CodingProblem
    research: ResearchIntel | None = None
    user_weaknesses: list[str] = Field(default_factory=list)


class AxisScore(BaseModel):
    score: int
    comment: str


class ScorecardAxes(BaseModel):
    technical_correctness: AxisScore
    process_of_thought: AxisScore
    curiosity: AxisScore
    self_presentation: AxisScore
    closing_questions: AxisScore
    code_quality: AxisScore


class ScorecardV2(BaseModel):
    overall_score: int
    axes: ScorecardAxes
    strengths: list[str]
    areas_to_improve: list[str]
    recommendation: str


class InterviewPipelineResult(BaseModel):
    parsed_jd: ParsedJD | None = None
    problem: CodingProblem | None = None   # None until background task completes
    raw_problem: dict | None = None        # {title, difficulty, description} — available immediately
    persona: PersonaVoice
    research: ResearchIntel | None = None

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


class PersonaOutput(BaseModel):
    persona_text: str
    question_bank: QuestionBank
    prep_plan: str
    oa_platform: str | None = None


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

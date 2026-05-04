from app.agents.problem import ProblemAgent
from app.agents.parser import ParseAgent
from app.agents.persona import PersonaAgent
from app.agents.scorer import ScorerAgent
from app.agents.schemas import (
    CodingProblem,
    InterviewPipelineResult,
    ParseInput,
    PersonaInput,
    PersonaVoice,
    PersonaVoiceInput,
    PipelineResult,
    ProblemInput,
    ParsedJD,
    ResearchIntel,
    ScorecardV2,
    ScorecardResult,
    ScorerInput,
)
from app.services.llm import LLMService
from app.services.research import ResearchService


class Orchestrator:
    def __init__(self, llm: LLMService, research: ResearchService | None = None) -> None:
        self.parser = ParseAgent(llm)
        self.problem_agent = ProblemAgent(llm)
        self.persona = PersonaAgent(llm)
        self.scorer = ScorerAgent(llm)
        self.research = research
        self.llm = llm

    async def run_jd_pipeline(
        self,
        jd_raw: str,
        user_weaknesses: list[str] | None = None,
        cv_text: str | None = None,
    ) -> PipelineResult:
        parsed = await self.parser.run(ParseInput(jd_raw=jd_raw))

        research_intel = None
        if self.research:
            try:
                raw = await self.research.search(parsed.company, parsed.role)
                if not raw.get("no_results"):
                    research_intel = ResearchIntel(**raw)
            except Exception:
                research_intel = None

        persona_output = await self.persona.run(
            PersonaInput(
                parsed_jd=parsed,
                research=research_intel,
                user_weaknesses=user_weaknesses or [],
                cv_text=cv_text,
            )
        )

        return PipelineResult(
            parsed_jd=parsed,
            persona=persona_output,
            research=research_intel,
        )

    async def run_scoring(self, messages: list[dict], persona: str) -> ScorecardResult:
        return await self.scorer.run(ScorerInput(messages=messages, persona=persona))

    async def run_interview_pipeline(
        self,
        source: str,
        content: str,
        difficulty: str = "medium",
        user_weaknesses: list[str] | None = None,
    ) -> InterviewPipelineResult:
        _ = difficulty
        parsed_jd: ParsedJD | None = None

        if source == "jd":
            parsed_jd = await self.parser.run(ParseInput(jd_raw=content))

        # Fast phase only — scrape raw problem, no LLM paraphrase/codegen yet
        from app.agents.schemas import ProblemInput
        raw_problem = await self.problem_agent.fetch_raw(
            ProblemInput(
                source=source,
                content=content,
                parsed_jd=parsed_jd,
                user_weaknesses=user_weaknesses or [],
            )
        )

        # Hardcoded Elon persona — saves 1 LLM call at session start
        persona = PersonaVoice(
            persona_text=(
                "You are Elon Musk conducting a technical interview. "
                "Be direct, impatient, and think from first principles. "
                "Ask sharp questions. Cut through fluff immediately."
            ),
            oa_platform=None,
        )

        return InterviewPipelineResult(
            parsed_jd=parsed_jd,
            problem=None,        # filled in by background task
            raw_problem=raw_problem,
            persona=persona,
            research=None,
        )

    async def run_six_axis_scoring(
        self,
        messages: list[dict],
        persona: str,
        problem: CodingProblem | None = None,
    ) -> ScorecardV2:
        return await self.scorer.score_six_axes(
            messages=messages,
            persona=persona,
            problem=problem,
        )

    async def build_problem_persona(self, problem: dict) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are creating a realistic technical interviewer character for a coding round. "
                    "Give them a name and a brief personality. They are concise, professional, "
                    "and focused on evaluating problem-solving approach, code quality, and communication."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Build a coding interviewer persona for this problem:\n"
                    f"Title: {problem['title']}\n"
                    f"Difficulty: {problem['difficulty']}"
                ),
            },
        ]
        return await self.llm.complete(messages)

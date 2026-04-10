from app.agents.parser import ParseAgent
from app.agents.persona import PersonaAgent
from app.agents.scorer import ScorerAgent
from app.agents.schemas import (
    ParseInput,
    PersonaInput,
    PipelineResult,
    ResearchIntel,
    ScorecardResult,
    ScorerInput,
)
from app.services.llm import LLMService
from app.services.research import ResearchService


class Orchestrator:
    def __init__(self, llm: LLMService, research: ResearchService | None = None) -> None:
        self.parser = ParseAgent(llm)
        self.persona = PersonaAgent(llm)
        self.scorer = ScorerAgent(llm)
        self.research = research
        self.llm = llm

    async def run_jd_pipeline(
        self,
        jd_raw: str,
        user_weaknesses: list[str] | None = None,
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
            )
        )

        return PipelineResult(
            parsed_jd=parsed,
            persona=persona_output,
            research=research_intel,
        )

    async def run_scoring(self, messages: list[dict], persona: str) -> ScorecardResult:
        return await self.scorer.run(ScorerInput(messages=messages, persona=persona))

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

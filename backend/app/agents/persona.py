import asyncio
import json

from app.agents.base import BaseAgent
from app.agents.schemas import (
    PersonaInput,
    PersonaOutput,
    PersonaVoice,
    PersonaVoiceInput,
    QuestionBank,
)
from app.services.jd import detect_oa_platform


class PersonaAgent(BaseAgent):
    name = "persona"
    description = "Builds interviewer persona, question bank, and prep plan"

    async def _build_persona(self, input_data: PersonaInput) -> str:
        parsed = input_data.parsed_jd
        skills = ", ".join(parsed.key_skills)
        research_line = ""
        if input_data.research and (
            input_data.research.culture_notes or input_data.research.common_questions
        ):
            research_line = (
                f"\nReal interview reports suggest: {input_data.research.culture_notes}. "
                f"Common questions: {input_data.research.common_questions}."
            )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert at designing realistic mock interview personas. "
                    "Create a specific, named interviewer character. "
                    "Describe their background, interview style, and what they look for."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Build an interviewer persona for:\n"
                    f"Company: {parsed.company}\n"
                    f"Role: {parsed.role}\n"
                    f"Level: {parsed.level}\n"
                    f"Key skills: {skills}"
                    f"{research_line}"
                ),
            },
        ]
        return await self.llm.complete(messages)

    async def _generate_question_bank(self, input_data: PersonaInput) -> QuestionBank:
        parsed = input_data.parsed_jd
        skills = ", ".join(parsed.key_skills)
        focus = ", ".join(parsed.focus_areas)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert technical interviewer. Generate a structured question "
                    "bank for a mock interview and return ONLY valid JSON.\n\n"
                    "Routing rules for coding.type:\n"
                    "- Infrastructure / Platform / DevOps / SRE / BaseOS → system_design\n"
                    "- General SWE / Backend / Frontend → leetcode\n"
                    "- Data Science / ML / AI → leetcode (stats/ML focus)\n"
                    "- Junior / Intern level → simpler questions, lighter coding round\n\n"
                    "Return JSON with exactly these keys:\n"
                    "warmup (list[str], 2 questions),\n"
                    "trivia (list[str], 4 role-specific technical questions),\n"
                    "culture_fit (list[str], 2 company-specific behavioral questions),\n"
                    "coding (object with: type (str), topic (str), hints (list[str], 2-3))"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Company: {parsed.company}\n"
                    f"Role: {parsed.role}\n"
                    f"Level: {parsed.level}\n"
                    f"Key skills: {skills}\n"
                    f"Focus areas: {focus}"
                ),
            },
        ]
        raw = await self.llm.complete(messages, json_mode=True)
        return QuestionBank.model_validate(json.loads(raw))

    async def _generate_prep_plan(self, input_data: PersonaInput) -> str:
        parsed = input_data.parsed_jd
        focus = ", ".join(parsed.focus_areas)
        weakness_line = ""
        if input_data.user_weaknesses:
            weakness_line = (
                f"\nThe candidate has previously struggled with: {', '.join(input_data.user_weaknesses)}. "
                "Emphasize these areas."
            )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a senior career coach. Create a focused, actionable interview "
                    "prep plan. Use a numbered list. Be specific and prioritised."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Create a prep plan for:\n"
                    f"Company: {parsed.company}\n"
                    f"Role: {parsed.role}\n"
                    f"Level: {parsed.level}\n"
                    f"Focus areas: {focus}"
                    f"{weakness_line}"
                ),
            },
        ]
        return await self.llm.complete(messages)

    async def build_voice(self, input_data: PersonaVoiceInput) -> PersonaVoice:
        company = "Unknown"
        role = "Unknown"
        level = "Unknown"
        if input_data.parsed_jd:
            company = input_data.parsed_jd.company
            role = input_data.parsed_jd.role
            level = input_data.parsed_jd.level

        research_line = ""
        if input_data.research and (
            input_data.research.culture_notes or input_data.research.common_questions
        ):
            research_line = (
                f"\nCulture notes: {input_data.research.culture_notes}. "
                f"Common interview question patterns: {input_data.research.common_questions}."
            )

        weakness_line = ""
        if input_data.user_weaknesses:
            weakness_line = (
                f"\nProbe these likely weak areas naturally during the interview: "
                f"{', '.join(input_data.user_weaknesses)}."
            )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are designing a realistic interviewer character for a coding interview. "
                    "Give them a name and 2-3 sentences of personality + style. "
                    "They must NOT reveal the problem's hidden details unless asked."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Company: {company}, Role: {role}, Level: {level}.\n"
                    f"Problem: {input_data.problem.title} ({input_data.problem.difficulty})."
                    f"{research_line}"
                    f"{weakness_line}\n"
                    "Return just the persona description, no JSON."
                ),
            },
        ]

        persona_text = await self.llm.complete(messages)
        oa_platform = detect_oa_platform(company) if input_data.parsed_jd else None
        return PersonaVoice(persona_text=persona_text, oa_platform=oa_platform)

    async def run(self, input_data: PersonaInput) -> PersonaOutput:
        persona_text, question_bank, prep_plan = await asyncio.gather(
            self._build_persona(input_data),
            self._generate_question_bank(input_data),
            self._generate_prep_plan(input_data),
        )
        oa_platform = detect_oa_platform(
            f"{input_data.parsed_jd.company} {input_data.parsed_jd.role} {input_data.parsed_jd.focus_areas}"
        )
        return PersonaOutput(
            persona_text=persona_text,
            question_bank=question_bank,
            prep_plan=prep_plan,
            oa_platform=oa_platform,
        )

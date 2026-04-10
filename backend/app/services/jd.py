import asyncio
import json
import re
from app.services.llm import LLMService
from app.services.research import ResearchService
from app.core.logging import setup_logger

logger = setup_logger(__name__)

OA_PLATFORM_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bhackerrank\b", re.IGNORECASE), "HackerRank"),
    (re.compile(r"\bcodesignal\b", re.IGNORECASE), "CodeSignal"),
    (re.compile(r"\bkarat\b", re.IGNORECASE), "Karat"),
    (re.compile(r"\bcoderpad\b", re.IGNORECASE), "CoderPad"),
    (re.compile(r"\bleetcode\b", re.IGNORECASE), "LeetCode"),
    (re.compile(r"\btriplebyte\b", re.IGNORECASE), "Triplebyte"),
    (re.compile(r"\bcodility\b", re.IGNORECASE), "Codility"),
]


def detect_oa_platform(jd_raw: str) -> str | None:
    first_match_name: str | None = None
    first_match_index: int | None = None
    for pattern, canonical_name in OA_PLATFORM_PATTERNS:
        match = pattern.search(jd_raw)
        if not match:
            continue
        if first_match_index is None or match.start() < first_match_index:
            first_match_index = match.start()
            first_match_name = canonical_name
    return first_match_name


class JDService:
    def __init__(self, llm: LLMService, research: ResearchService | None = None) -> None:
        self.llm = llm
        self.research = research

    async def parse_jd(self, jd_raw: str) -> dict:
        """Step 1 — extract structured info from a raw job description."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a job description parser. Extract structured information "
                    "and return ONLY valid JSON with these keys: "
                    "company (string), role (string), level (string: junior/mid/senior/staff), "
                    "key_skills (list of strings), focus_areas (list of strings)."
                ),
            },
            {"role": "user", "content": f"Parse this job description:\n\n{jd_raw}"},
        ]
        raw = await self.llm.complete(messages, json_mode=True)
        return json.loads(raw)

    async def build_persona(self, parsed: dict) -> str:
        """Step 2 — build a specific interviewer persona from parsed JD data."""
        skills = ", ".join(parsed.get("key_skills", []))
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
                    f"Company: {parsed.get('company')}\n"
                    f"Role: {parsed.get('role')}\n"
                    f"Level: {parsed.get('level')}\n"
                    f"Key skills: {skills}"
                ),
            },
        ]
        return await self.llm.complete(messages)

    async def generate_prep_plan(self, parsed: dict) -> str:
        """Step 3 — generate a ranked prep plan for the candidate."""
        focus = ", ".join(parsed.get("focus_areas", []))
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
                    f"Company: {parsed.get('company')}\n"
                    f"Role: {parsed.get('role')}\n"
                    f"Level: {parsed.get('level')}\n"
                    f"Focus areas: {focus}"
                ),
            },
        ]
        return await self.llm.complete(messages)

    async def generate_question_bank(self, parsed: dict) -> dict:
        """Step 3 — generate a structured question bank for the interview.

        Routing: decides coding round type (leetcode vs system_design) based
        on role and level so each interview is tailored to the position.
        """
        skills = ", ".join(parsed.get("key_skills", []))
        focus = ", ".join(parsed.get("focus_areas", []))
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
                    f"Company: {parsed.get('company')}\n"
                    f"Role: {parsed.get('role')}\n"
                    f"Level: {parsed.get('level')}\n"
                    f"Key skills: {skills}\n"
                    f"Focus areas: {focus}"
                ),
            },
        ]
        raw = await self.llm.complete(messages, json_mode=True)
        return json.loads(raw)

    async def build_problem_persona(self, problem: dict) -> str:
        """Build a coding interviewer persona for a LeetCode-style problem session."""
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

    async def process_jd(self, jd_raw: str) -> tuple[dict, str, dict, str, str | None]:
        """Parallelization: parse JD, then gather persona + question bank + prep plan concurrently."""
        parsed = await self.parse_jd(jd_raw)
        tasks = [
            self.build_persona(parsed),
            self.generate_question_bank(parsed),
            self.generate_prep_plan(parsed),
        ]
        if self.research:
            tasks.append(self.research.search(parsed.get("company", ""), parsed.get("role", "")))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        if len(results) < 3 or any(isinstance(r, Exception) for r in results[:3]):
            first_exception = next((r for r in results if isinstance(r, Exception)), RuntimeError("JD pipeline failed"))
            raise first_exception

        persona = results[0]
        question_bank = results[1]
        prep_plan = results[2]
        oa_platform = detect_oa_platform(jd_raw)
        return parsed, persona, question_bank, prep_plan, oa_platform

    async def generate_scorecard(self, messages: list[dict], persona: str) -> str:
        """Reflection pattern: draft scorecard → self-critique → refined final."""
        transcript = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in messages
        )

        # Step 1 — draft
        draft = await self.llm.complete(
            [
                {
                    "role": "system",
                    "content": (
                        f"{persona}\n\n"
                        "You just finished a mock interview. Score the candidate and return "
                        "ONLY valid JSON with: overall_score (int 1-10), "
                        "strengths (list of strings), areas_to_improve (list of strings), "
                        "recommendation (string: hire/no_hire/strong_hire)."
                    ),
                },
                {"role": "user", "content": f"Interview transcript:\n\n{transcript}"},
            ],
            json_mode=True,
        )

        # Step 2 — reflect and refine
        refined = await self.llm.complete(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a calibration reviewer for interview scorecards. "
                        "You will receive a draft scorecard and the original interview transcript. "
                        "Check for: score inflation/deflation, missed strengths, missed weaknesses, "
                        "inconsistency between scores and evidence. "
                        "Return an improved version as ONLY valid JSON with the same keys: "
                        "overall_score (int 1-10), strengths (list), areas_to_improve (list), "
                        "recommendation (hire/no_hire/strong_hire)."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Draft scorecard:\n{draft}\n\n"
                        f"Interview transcript:\n{transcript}"
                    ),
                },
            ],
            json_mode=True,
        )
        return refined

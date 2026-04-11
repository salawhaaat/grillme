import json
import random
from typing import Any

from app.agents.base import BaseAgent
from app.agents.schemas import CodingProblem, ParsedJD, ProblemInput
from app.services.llm import LLMService
from app.services.question_bank import QuestionBankService, QuestionEntry
from app.services.scraper import ScraperService


class ProblemAgent(BaseAgent):
    name = "problem"
    description = "Generates a cut coding problem from JD / URL / pasted text"

    def __init__(
        self,
        llm: LLMService,
        scraper: ScraperService | None = None,
        question_bank: QuestionBankService | None = None,
    ) -> None:
        super().__init__(llm)
        self.scraper = scraper or ScraperService()
        self.question_bank = question_bank or QuestionBankService()

    async def run(self, input_data: ProblemInput) -> CodingProblem:
        source = input_data.source
        if source == "jd":
            if not input_data.parsed_jd:
                raise ValueError("parsed_jd required for jd source")
            slug = await self._pick_slug_for_company(
                input_data.parsed_jd,
                user_weaknesses=input_data.user_weaknesses,
            )
            full = await self.scraper.scrape(f"https://leetcode.com/problems/{slug}/")
            if not full:
                full = {
                    "title": "Two Sum",
                    "difficulty": "Easy",
                    "description": (
                        "Given an array of integers nums and an integer target, return indices "
                        "of the two numbers such that they add up to target."
                    ),
                }
        elif source == "url":
            full = await self.scraper.scrape(input_data.content)
            if not full:
                raise ValueError("Could not scrape URL")
        else:
            full = {
                "title": "Custom Problem",
                "difficulty": "Medium",
                "description": input_data.content,
            }

        cut = await self._paraphrase_and_cut(full)
        generated = await self._generate_code_and_tests(full)

        return CodingProblem(
            title=full["title"],
            difficulty=full["difficulty"],
            problem_statement=cut,
            full_problem=full["description"],
            starter_code=generated["starter_code"],
            test_cases=generated["test_cases"],
            method_name=generated["method_name"],
        )

    async def _pick_slug_for_company(
        self,
        parsed: ParsedJD,
        user_weaknesses: list[str] | None = None,
    ) -> str:
        candidates = self.question_bank.get_for_company(parsed.company or "")
        if candidates:
            return self._weighted_pick(candidates, user_weaknesses or [])
        return await self._llm_guess_slug(parsed)

    def _weighted_pick(self, candidates: list[QuestionEntry], weaknesses: list[str]) -> str:
        weights: list[float] = []
        for entry in candidates:
            weight = float(entry.frequency)
            if weaknesses:
                boosted = False
                for weakness in weaknesses:
                    weakness_lower = weakness.lower()
                    for topic in entry.topics:
                        topic_lower = topic.lower()
                        if weakness_lower in topic_lower or topic_lower in weakness_lower:
                            weight *= 2.0
                            boosted = True
                            break
                    if boosted:
                        break
            weights.append(weight)
        chosen = random.choices(candidates, weights=weights, k=1)[0]
        return chosen.slug

    async def _llm_guess_slug(self, parsed: ParsedJD) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a LeetCode expert. Given a company and role, pick ONE real LeetCode "
                    "problem slug that matches the company's typical interview style.\n"
                    "Examples of real slugs: 'two-sum', 'longest-substring-without-repeating-characters', "
                    "'word-ladder', 'lru-cache', 'merge-k-sorted-lists', 'course-schedule', "
                    "'number-of-islands'.\n"
                    "Return ONLY valid JSON: {\"slug\": \"<kebab-case-slug>\", \"reason\": \"<why this fits>\"}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Company: {parsed.company}\n"
                    f"Role: {parsed.role}\n"
                    f"Level: {parsed.level}\n"
                    f"Key skills: {', '.join(parsed.key_skills)}\n"
                    f"Focus areas: {', '.join(parsed.focus_areas)}"
                ),
            },
        ]
        raw = await self.llm.complete(messages, json_mode=True)
        data = json.loads(raw)
        return data.get("slug", "two-sum")

    async def _paraphrase_and_cut(self, full: dict[str, Any]) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an interviewer presenting a coding problem. Rewrite the problem in your own voice, "
                    "2-3 sentences MAX. You MUST REMOVE:\n"
                    "- Example inputs/outputs\n"
                    "- Constraint bounds (array length, value ranges, etc.)\n"
                    "- Edge case notes (empty arrays, duplicates, negative numbers, etc.)\n"
                    "- Return format specifics (what order, how to handle ties)\n"
                    "Keep ONLY the core task. The candidate should have to ASK to learn the details.\n"
                    "Do not say 'in this problem' or 'your task is'. Just state the task directly."
                ),
            },
            {
                "role": "user",
                "content": f"Problem: {full['title']}\n\n{full['description']}",
            },
        ]
        return await self.llm.complete(messages)

    async def _generate_code_and_tests(self, full: dict[str, Any]) -> dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a LeetCode test generator. Given a problem, generate:\n"
                    "1. method_name (camelCase, as LeetCode uses)\n"
                    "2. starter_code — Python class Solution with method signature and type hints, body is `pass`\n"
                    "3. test_cases — 5-8 cases covering basic, edge, and tricky inputs\n\n"
                    "Return ONLY JSON: {\"method_name\": str, \"starter_code\": str, "
                    "\"test_cases\": [{\"input\": [...], \"expected\": ...}, ...]}"
                ),
            },
            {
                "role": "user",
                "content": f"Problem: {full['title']}\nDifficulty: {full['difficulty']}\n\n{full['description']}",
            },
        ]
        raw = await self.llm.complete(messages, json_mode=True)
        return json.loads(raw)

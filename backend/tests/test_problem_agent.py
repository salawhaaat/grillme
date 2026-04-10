import json
from unittest.mock import AsyncMock

import pytest

from app.agents.problem import ProblemAgent
from app.agents.schemas import CodingProblem, ParsedJD, ProblemInput
from app.services.llm import LLMService
from app.services.scraper import ScraperService


def _problem_dict() -> dict:
    return {
        "title": "Two Sum",
        "difficulty": "Easy",
        "description": (
            "Given an array of integers nums and an integer target, return indices "
            "of the two numbers such that they add up to target."
        ),
    }


def _parsed_jd() -> ParsedJD:
    return ParsedJD(
        company="Stripe",
        role="Backend Engineer",
        level="senior",
        key_skills=["Python", "Algorithms"],
        focus_areas=["data structures", "problem solving"],
    )


def _codegen_payload() -> str:
    return json.dumps(
        {
            "method_name": "twoSum",
            "starter_code": (
                "class Solution:\n"
                "    def twoSum(self, nums: list[int], target: int) -> list[int]:\n"
                "        pass\n"
            ),
            "test_cases": [
                {"input": [[2, 7, 11, 15], 9], "expected": [0, 1]},
                {"input": [[3, 2, 4], 6], "expected": [1, 2]},
            ],
        }
    )


async def test_problem_agent_run_text_source_returns_coding_problem():
    llm = AsyncMock(spec=LLMService)
    llm.complete.side_effect = ["Find two numbers that sum to a target.", _codegen_payload()]
    scraper = AsyncMock(spec=ScraperService)
    agent = ProblemAgent(llm=llm, scraper=scraper)

    result = await agent.run(
        ProblemInput(source="text", content="Given nums and target, return indices.")
    )

    assert isinstance(result, CodingProblem)
    assert result.title == "Custom Problem"
    assert result.problem_statement == "Find two numbers that sum to a target."
    assert result.method_name == "twoSum"
    assert result.test_cases[0]["expected"] == [0, 1]


async def test_problem_agent_run_url_source_uses_scraper_result():
    llm = AsyncMock(spec=LLMService)
    llm.complete.side_effect = ["Cut prompt", _codegen_payload()]
    scraper = AsyncMock(spec=ScraperService)
    scraper.scrape.return_value = _problem_dict()
    agent = ProblemAgent(llm=llm, scraper=scraper)

    result = await agent.run(
        ProblemInput(source="url", content="https://leetcode.com/problems/two-sum/")
    )

    assert isinstance(result, CodingProblem)
    assert result.title == "Two Sum"
    assert result.difficulty == "Easy"
    assert result.full_problem.startswith("Given an array of integers")
    scraper.scrape.assert_awaited_once()


async def test_problem_agent_run_jd_source_picks_slug_and_builds_problem():
    llm = AsyncMock(spec=LLMService)
    llm.complete.side_effect = [
        json.dumps({"slug": "two-sum", "reason": "classic for backend screens"}),
        "Cut version",
        _codegen_payload(),
    ]
    scraper = AsyncMock(spec=ScraperService)
    scraper.scrape.return_value = _problem_dict()
    agent = ProblemAgent(llm=llm, scraper=scraper)

    result = await agent.run(
        ProblemInput(source="jd", content="JD raw text", parsed_jd=_parsed_jd())
    )

    assert isinstance(result, CodingProblem)
    assert result.title == "Two Sum"
    assert result.method_name == "twoSum"
    scraper.scrape.assert_awaited_once_with("https://leetcode.com/problems/two-sum/")


async def test_problem_agent_run_jd_source_requires_parsed_jd():
    llm = AsyncMock(spec=LLMService)
    scraper = AsyncMock(spec=ScraperService)
    agent = ProblemAgent(llm=llm, scraper=scraper)

    with pytest.raises(ValueError, match="parsed_jd required for jd source"):
        await agent.run(ProblemInput(source="jd", content="JD raw text", parsed_jd=None))


async def test_problem_agent_run_url_source_raises_on_scraper_failure():
    llm = AsyncMock(spec=LLMService)
    scraper = AsyncMock(spec=ScraperService)
    scraper.scrape.return_value = None
    agent = ProblemAgent(llm=llm, scraper=scraper)

    with pytest.raises(ValueError, match="Could not scrape URL"):
        await agent.run(ProblemInput(source="url", content="https://example.com/problem"))


async def test_paraphrase_and_cut_prompt_requires_removing_examples_constraints():
    llm = AsyncMock(spec=LLMService)
    llm.complete.return_value = "Cut problem statement"
    agent = ProblemAgent(llm=llm, scraper=AsyncMock(spec=ScraperService))

    await agent._paraphrase_and_cut(_problem_dict())

    system_prompt = llm.complete.call_args.args[0][0]["content"]
    assert "You MUST REMOVE" in system_prompt
    assert "Example inputs/outputs" in system_prompt
    assert "Constraint bounds" in system_prompt

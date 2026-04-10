import json

from app.agents.base import BaseAgent
from app.agents.schemas import CodingProblem, ScorecardV2, ScorecardResult, ScorerInput


class ScorerAgent(BaseAgent):
    name = "scorer"
    description = "Generates calibrated interview scorecard using reflection"

    @staticmethod
    def _compute_weighted_overall(scorecard: ScorecardV2) -> int:
        axes = scorecard.axes
        weighted = (
            axes.technical_correctness.score * 0.25
            + axes.process_of_thought.score * 0.20
            + axes.curiosity.score * 0.15
            + axes.self_presentation.score * 0.15
            + axes.closing_questions.score * 0.10
            + axes.code_quality.score * 0.15
        )
        return round(weighted)

    async def score_six_axes(
        self,
        messages: list[dict],
        persona: str,
        problem: CodingProblem | None = None,
    ) -> ScorecardV2:
        transcript = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
        problem_line = ""
        if problem:
            problem_line = (
                f"\nProblem context:\n"
                f"Title: {problem.title}\n"
                f"Difficulty: {problem.difficulty}\n"
                f"Statement: {problem.problem_statement}"
            )

        draft = await self.llm.complete(
            [
                {
                    "role": "system",
                    "content": (
                        f"{persona}\n\n"
                        "You just finished a mock interview. Score the candidate and return ONLY valid JSON "
                        "with this exact shape:\n"
                        "{\n"
                        '  "overall_score": int,\n'
                        '  "axes": {\n'
                        '    "technical_correctness": {"score": int, "comment": str},\n'
                        '    "process_of_thought": {"score": int, "comment": str},\n'
                        '    "curiosity": {"score": int, "comment": str},\n'
                        '    "self_presentation": {"score": int, "comment": str},\n'
                        '    "closing_questions": {"score": int, "comment": str},\n'
                        '    "code_quality": {"score": int, "comment": str}\n'
                        "  },\n"
                        '  "strengths": [str],\n'
                        '  "areas_to_improve": [str],\n'
                        '  "recommendation": "hire" | "no_hire" | "strong_hire"\n'
                        "}\n\n"
                        "All axis scores must be integers from 0 to 10 with one-line comments.\n"
                        "If the candidate's first user message is code or a solution attempt "
                        "(not a clarifying question about the problem),\n"
                        "cap `curiosity.score` at 4 and note it in the comment.\n"
                        "Only give `closing_questions.score` > 6 if the candidate asked thoughtful, specific "
                        "questions about the team, role, tech stack, or what the interviewer cares about near "
                        "the end of the transcript. Generic 'what's your favorite part of working here' "
                        "should score ≤ 5."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Interview transcript:\n\n{transcript}{problem_line}",
                },
            ],
            json_mode=True,
        )

        refined = await self.llm.complete(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a calibration reviewer for interview scorecards. "
                        "Check for axis score drift. Rebalance if any single axis dominates the overall. "
                        "Return refined ScorecardV2 JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Draft scorecard:\n{draft}\n\n"
                        f"Interview transcript:\n{transcript}{problem_line}"
                    ),
                },
            ],
            json_mode=True,
        )

        parsed = ScorecardV2.model_validate(json.loads(refined))
        return parsed.model_copy(update={"overall_score": self._compute_weighted_overall(parsed)})

    async def run(self, input_data: ScorerInput) -> ScorecardResult:
        transcript = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in input_data.messages
        )

        draft = await self.llm.complete(
            [
                {
                    "role": "system",
                    "content": (
                        f"{input_data.persona}\n\n"
                        "You just finished a mock interview. Score the candidate and return "
                        "ONLY valid JSON with: overall_score (int 1-10), "
                        "strengths (list of strings), areas_to_improve (list of strings), "
                        "recommendation (string: hire/no_hire/strong_hire). "
                        "Evaluate the candidate's thought process while solving problems "
                        "(clarity, trade-offs, debugging path, communication). "
                        "Also evaluate closing-stage interview behavior: quality of questions asked "
                        "about team, product/problem space, and priorities/care-abouts."
                    ),
                },
                {"role": "user", "content": f"Interview transcript:\n\n{transcript}"},
            ],
            json_mode=True,
        )

        refined = await self.llm.complete(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a calibration reviewer for interview scorecards. "
                        "You will receive a draft scorecard and the original interview transcript. "
                        "Check for: score inflation/deflation, missed strengths, missed weaknesses, "
                        "inconsistency between scores and evidence, missing evaluation of thought process, "
                        "and missing closing-stage question quality. "
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

        return ScorecardResult.model_validate(json.loads(refined))

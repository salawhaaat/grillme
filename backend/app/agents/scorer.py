import json

from app.agents.base import BaseAgent
from app.agents.schemas import ScorecardResult, ScorerInput


class ScorerAgent(BaseAgent):
    name = "scorer"
    description = "Generates calibrated interview scorecard using reflection"

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

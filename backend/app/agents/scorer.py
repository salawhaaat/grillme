import json
import re

from app.agents.base import BaseAgent
from app.agents.schemas import AxisScore, CodingProblem, ScorecardAxes, ScorecardV2, ScorecardResult, ScorerInput


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

    @staticmethod
    def _extract_failed_generation(raw_error: str) -> str | None:
        match = re.search(r"'failed_generation':\s*'(.+)'", raw_error, flags=re.DOTALL)
        if not match:
            return None
        payload = match.group(1)
        payload = payload.replace("\\n", "\n").replace('\\"', '"')
        return payload

    async def _repair_json(self, malformed: str, schema_hint: str) -> str:
        return await self.llm.complete(
            [
                {
                    "role": "system",
                    "content": (
                        "Repair malformed JSON and return ONLY valid JSON. "
                        "Do not wrap in markdown fences.\n"
                        f"Schema:\n{schema_hint}"
                    ),
                },
                {"role": "user", "content": malformed},
            ],
            json_mode=False,
            temperature=0,
        )

    async def _parse_scorecard_v2(self, raw: str) -> ScorecardV2:
        schema_hint = (
            '{ "overall_score": int, "axes": {'
            '"technical_correctness":{"score":int,"comment":str},'
            '"process_of_thought":{"score":int,"comment":str},'
            '"curiosity":{"score":int,"comment":str},'
            '"self_presentation":{"score":int,"comment":str},'
            '"closing_questions":{"score":int,"comment":str},'
            '"code_quality":{"score":int,"comment":str}'
            '}, "strengths":[str], "areas_to_improve":[str], '
            '"recommendation":"hire"|"no_hire"|"strong_hire" }'
        )
        try:
            return ScorecardV2.model_validate(json.loads(raw))
        except Exception:
            repaired = await self._repair_json(raw, schema_hint)
            return ScorecardV2.model_validate(json.loads(repaired))

    async def score_six_axes(
        self,
        messages: list[dict],
        persona: str,
        problem: CodingProblem | None = None,
    ) -> ScorecardV2:
        transcript = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
        user_turns = sum(1 for m in messages if m.get("role") == "user")

        # Not enough data to score — return a neutral scorecard immediately
        if user_turns < 2:
            neutral_comment = "Insufficient interview data — candidate did not speak enough to evaluate this axis."
            scorecard = ScorecardV2(
                overall_score=5,
                axes=ScorecardAxes(
                    technical_correctness=AxisScore(score=5, comment=neutral_comment),
                    process_of_thought=AxisScore(score=5, comment=neutral_comment),
                    curiosity=AxisScore(score=5, comment=neutral_comment),
                    self_presentation=AxisScore(score=5, comment=neutral_comment),
                    closing_questions=AxisScore(score=5, comment=neutral_comment),
                    code_quality=AxisScore(score=5, comment=neutral_comment),
                ),
                strengths=[],
                areas_to_improve=["Complete a full interview session to receive meaningful feedback."],
                recommendation="no_hire",
            )
            return scorecard

        low_signal_line = (
            "\nIMPORTANT: This interview has very few candidate responses. "
            "You MUST write 'Insufficient data' in axis comments where there is no evidence. "
            "Do NOT invent or assume candidate behavior. Keep all scores between 4-6 unless "
            "there is direct evidence in the transcript."
            if user_turns < 5
            else ""
        )
        problem_line = ""
        if problem:
            problem_line = (
                f"\nProblem context:\n"
                f"Title: {problem.title}\n"
                f"Difficulty: {problem.difficulty}\n"
                f"Statement: {problem.problem_statement}"
            )

        draft_messages = [
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
                    "should score ≤ 5.\n"
                    f"{low_signal_line}"
                ),
            },
            {
                "role": "user",
                "content": f"Interview transcript:\n\n{transcript}{problem_line}",
            },
        ]
        try:
            draft = await self.llm.complete(draft_messages, json_mode=True, temperature=0)
        except Exception as e:
            draft = self._extract_failed_generation(str(e))
            if not draft:
                draft = await self.llm.complete(draft_messages, json_mode=False, temperature=0)

        # Skip the refine pass for local/ollama provider — it doubles latency for minimal gain
        # on small models. Only run refine for cloud providers with fast inference.
        provider = getattr(self.llm, '_active_provider', lambda: 'ollama')()
        if provider in ('ollama',):
            parsed = await self._parse_scorecard_v2(draft)
            return parsed.model_copy(update={"overall_score": self._compute_weighted_overall(parsed)})

        refine_messages = [
            {
                "role": "system",
                "content": (
                    "You are a calibration reviewer for interview scorecards. "
                    "Check for axis score drift. Rebalance if any single axis dominates the overall. "
                    "For short interviews, reduce overconfidence and avoid extreme penalties without evidence. "
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
        ]
        try:
            refined = await self.llm.complete(refine_messages, json_mode=True, temperature=0)
        except Exception as e:
            refined = self._extract_failed_generation(str(e))
            if not refined:
                refined = await self.llm.complete(refine_messages, json_mode=False, temperature=0)

        parsed = await self._parse_scorecard_v2(refined)
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

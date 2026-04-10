import json

from app.agents.base import BaseAgent
from app.agents.schemas import ParseInput, ParsedJD


class ParseAgent(BaseAgent):
    name = "parser"
    description = "Extracts structured data from raw job descriptions"

    async def run(self, input_data: ParseInput) -> ParsedJD:
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
            {"role": "user", "content": f"Parse this job description:\n\n{input_data.jd_raw}"},
        ]
        raw = await self.llm.complete(messages, json_mode=True)
        return ParsedJD.model_validate(json.loads(raw))

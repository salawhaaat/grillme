import json

from pydantic import BaseModel

from app.agents.base import BaseAgent
from app.agents.schemas import ScorecardResult


class MemoryAgent(BaseAgent):
    name = "memory"
    description = "Extracts weak areas from scorecard and manages cross-session learning"

    async def extract_weaknesses(self, scorecard: ScorecardResult) -> list[str]:
        messages = [
            {
                "role": "system",
                "content": (
                    "Given these interview improvement areas, extract 2-4 concise skill tags "
                    "(e.g., 'time complexity analysis', 'system design trade-offs', "
                    "'behavioral STAR format'). Return JSON: {tags: list[str]}"
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"areas_to_improve": scorecard.areas_to_improve}),
            },
        ]
        raw = await self.llm.complete(messages, json_mode=True)
        parsed = json.loads(raw)
        tags = parsed.get("tags", [])
        return [str(tag).strip() for tag in tags if str(tag).strip()]

    async def run(self, input_data: BaseModel) -> BaseModel:
        raise NotImplementedError("MemoryAgent.run is not used directly.")

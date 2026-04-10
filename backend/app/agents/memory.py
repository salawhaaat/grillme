import json
import re

from pydantic import BaseModel

from app.agents.base import BaseAgent
from app.agents.schemas import ScorecardResult


_CANONICAL_WEAKNESS_AREAS = {
    "communication",
    "problem solving",
    "system design",
    "time complexity",
    "coding speed",
    "debugging",
    "leadership",
}

_ALIASES = {
    "communication skills": "communication",
    "verbal communication": "communication",
    "behavioral star format": "communication",
    "behavioral": "communication",
    "algorithms": "problem solving",
    "algorithmic thinking": "problem solving",
    "problem-solving": "problem solving",
    "system design trade-offs": "system design",
    "architecture design": "system design",
    "time complexity analysis": "time complexity",
    "big o": "time complexity",
    "optimization": "time complexity",
    "coding pace": "coding speed",
    "implementation speed": "coding speed",
    "bug fixing": "debugging",
    "troubleshooting": "debugging",
    "ownership": "leadership",
    "stakeholder communication": "leadership",
}

_KEYWORD_MAP: list[tuple[tuple[str, ...], str]] = [
    (("communication", "behavioral", "star"), "communication"),
    (("algorithm", "problem solving"), "problem solving"),
    (("system design", "architecture", "trade-off", "scalability"), "system design"),
    (("time complexity", "big o", "complexity"), "time complexity"),
    (("speed", "pace", "slow"), "coding speed"),
    (("debug", "bug", "root cause"), "debugging"),
    (("leadership", "ownership", "stakeholder"), "leadership"),
]


def _normalize_text(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text.strip().lower())
    return collapsed.replace("_", " ").replace("-", " ")


def _map_to_canonical_area(text: str) -> str | None:
    normalized = _normalize_text(text)
    if not normalized or len(normalized) > 60:
        return None

    if normalized in _CANONICAL_WEAKNESS_AREAS:
        return normalized
    if normalized in _ALIASES:
        return _ALIASES[normalized]

    for keywords, area in _KEYWORD_MAP:
        if any(keyword in normalized for keyword in keywords):
            return area
    return None


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
        tags: list[str] = []
        raw = await self.llm.complete(messages, json_mode=True)
        try:
            parsed = json.loads(raw)
            raw_tags = parsed.get("tags", [])
            if isinstance(raw_tags, list):
                tags = [str(tag) for tag in raw_tags]
        except (json.JSONDecodeError, TypeError):
            tags = []

        seen: set[str] = set()
        normalized_tags: list[str] = []
        for tag in tags:
            canonical = _map_to_canonical_area(tag)
            if canonical and canonical not in seen:
                seen.add(canonical)
                normalized_tags.append(canonical)

        # Fallback to deterministic keyword extraction when LLM tags are empty/noisy.
        if not normalized_tags:
            for area_text in scorecard.areas_to_improve:
                canonical = _map_to_canonical_area(area_text)
                if canonical and canonical not in seen:
                    seen.add(canonical)
                    normalized_tags.append(canonical)

        return normalized_tags[:4]

    async def run(self, input_data: BaseModel) -> BaseModel:
        raise NotImplementedError("MemoryAgent.run is not used directly.")

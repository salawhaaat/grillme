import json
from pathlib import Path

from pydantic import BaseModel

DATA_PATH = Path(__file__).parent.parent / "data" / "company_questions.json"


class QuestionEntry(BaseModel):
    title: str
    slug: str
    difficulty: str
    frequency: int
    sources: list[str]
    topics: list[str]
    last_seen: str


class QuestionBankService:
    def __init__(self, path: Path = DATA_PATH) -> None:
        self.path = path
        self._data: dict[str, list[QuestionEntry]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._data = {}
            return
        raw = json.loads(self.path.read_text())
        self._data = {
            company.lower(): [QuestionEntry(**entry) for entry in entries]
            for company, entries in raw.items()
        }

    def get_for_company(self, company: str) -> list[QuestionEntry]:
        """Returns entries for a company sorted by frequency desc. Empty list if company unknown."""
        if not company:
            return []

        key = company.lower().strip()
        if key in self._data:
            return sorted(self._data[key], key=lambda entry: entry.frequency, reverse=True)

        for bank_key, entries in self._data.items():
            if bank_key in key or key in bank_key:
                return sorted(entries, key=lambda entry: entry.frequency, reverse=True)

        return []

    def companies(self) -> list[str]:
        return list(self._data.keys())

    def reload(self) -> None:
        """Re-read the JSON file (used after CLI refresh)."""
        self._load()

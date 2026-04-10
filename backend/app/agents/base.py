from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.services.llm import LLMService


class BaseAgent(ABC):
    name: str
    description: str

    def __init__(self, llm: LLMService) -> None:
        self.llm = llm

    @abstractmethod
    async def run(self, input_data: BaseModel) -> BaseModel:
        ...

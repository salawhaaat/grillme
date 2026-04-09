from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.services.llm import LLMService, RateLimitError, ProviderError
from app.core.logging import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])
llm = LLMService()


class ChatRequest(BaseModel):
    messages: list[dict]


@router.post("/stream")
async def stream_chat(body: ChatRequest) -> StreamingResponse:
    async def generate():
        try:
            async for chunk in llm.stream_chat(body.messages):
                yield chunk
        except RateLimitError as e:
            logger.warning("LLM rate limit: %s", e)
            yield "\n\n[error:429] LLM quota exceeded — try again later"
        except (ProviderError, ValueError) as e:
            logger.error("LLM provider error: %s", e)
            yield f"\n\n[error:503] {e}"

    return StreamingResponse(generate(), media_type="text/plain")

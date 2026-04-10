import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.session import InterviewSession
from app.services.sandbox import RunResult, SandboxService, TestResult

router = APIRouter(prefix="/api/code", tags=["code"])
sandbox = SandboxService()


class RunCodeRequest(BaseModel):
    code: str
    stdin_input: str = ""


class TestCodeRequest(BaseModel):
    code: str
    session_id: int


class ShareCodeRequest(BaseModel):
    session_id: int
    code: str
    run_result: RunResult | None = None
    test_result: TestResult | None = None


@router.post("/run", response_model=RunResult)
async def run_code(body: RunCodeRequest) -> RunResult:
    return await sandbox.run_code(code=body.code, stdin_input=body.stdin_input)


@router.post("/test", response_model=TestResult)
async def run_tests(
    body: TestCodeRequest,
    db: AsyncSession = Depends(get_db),
) -> TestResult:
    session = await db.get(InterviewSession, body.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if not session.test_cases:
        raise HTTPException(400, "Session has no test_cases")

    test_payload = json.loads(session.test_cases)
    method_name = test_payload.get("method_name") or session.method_name
    if not method_name:
        raise HTTPException(400, "Session has no method_name")

    return await sandbox.run_tests(
        code=body.code,
        test_cases=test_payload.get("test_cases", []),
        method_name=method_name,
    )


@router.post("/share")
async def share_code(
    body: ShareCodeRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await db.get(InterviewSession, body.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    messages = json.loads(session.messages) if session.messages else []
    block = f"[CODE UPDATE]\n```python\n{body.code}\n```"
    if body.run_result:
        block += (
            f"\n[RUN]\nexit_code={body.run_result.exit_code} timed_out={body.run_result.timed_out} "
            f"runtime_ms={body.run_result.runtime_ms}\nstdout:\n{body.run_result.stdout}\n"
            f"stderr:\n{body.run_result.stderr}"
        )
    if body.test_result:
        block += (
            f"\n[TESTS]\npassed={body.test_result.passed} failed={body.test_result.failed} "
            f"total={body.test_result.total} runtime_ms={body.test_result.runtime_ms}"
        )
    messages.append({"role": "system", "content": block})
    session.messages = json.dumps(messages)
    await db.commit()
    return {"ok": True}

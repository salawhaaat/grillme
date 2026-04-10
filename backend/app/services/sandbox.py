import asyncio
import json
import tempfile
import time
from pathlib import Path

from pydantic import BaseModel

MAX_TIMEOUT = 10
MAX_OUTPUT = 10_000


class RunResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    runtime_ms: int
    timed_out: bool = False


class TestCaseResult(BaseModel):
    id: int
    passed: bool
    input: str
    expected: str
    actual: str
    error: str | None = None


class TestResult(BaseModel):
    passed: int
    failed: int
    total: int
    results: list[TestCaseResult]
    runtime_ms: int


class SandboxService:
    async def run_code(
        self,
        code: str,
        stdin_input: str = "",
        timeout: int = MAX_TIMEOUT,
    ) -> RunResult:
        with tempfile.TemporaryDirectory() as tmpdir:
            code_path = Path(tmpdir) / "solution.py"
            code_path.write_text(code)
            start = time.monotonic()
            proc = await asyncio.create_subprocess_exec(
                "python3",
                str(code_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=tmpdir,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(input=stdin_input.encode() if stdin_input else None),
                    timeout=timeout,
                )
                elapsed = int((time.monotonic() - start) * 1000)
                return RunResult(
                    stdout=stdout_b.decode()[:MAX_OUTPUT],
                    stderr=stderr_b.decode()[:MAX_OUTPUT],
                    exit_code=proc.returncode or 0,
                    runtime_ms=elapsed,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return RunResult(
                    stdout="",
                    stderr=f"Timed out after {timeout}s",
                    exit_code=-1,
                    runtime_ms=int((time.monotonic() - start) * 1000),
                    timed_out=True,
                )

    async def run_tests(self, code: str, test_cases: list[dict], method_name: str) -> TestResult:
        harness = self._build_harness(code, test_cases, method_name)
        result = await self.run_code(harness)

        if result.timed_out:
            return TestResult(
                passed=0,
                failed=len(test_cases),
                total=len(test_cases),
                results=[
                    TestCaseResult(
                        id=i + 1,
                        passed=False,
                        input=str(tc.get("input", "")),
                        expected=str(tc.get("expected", "")),
                        actual="",
                        error="Timed out",
                    )
                    for i, tc in enumerate(test_cases)
                ],
                runtime_ms=result.runtime_ms,
            )

        try:
            data = json.loads(result.stdout)
            return TestResult(
                passed=data["passed"],
                failed=data["total"] - data["passed"],
                total=data["total"],
                results=[TestCaseResult(**r) for r in data["results"]],
                runtime_ms=result.runtime_ms,
            )
        except (json.JSONDecodeError, KeyError):
            return TestResult(
                passed=0,
                failed=max(1, len(test_cases)),
                total=max(1, len(test_cases)),
                results=[
                    TestCaseResult(
                        id=1,
                        passed=False,
                        input="",
                        expected="",
                        actual="",
                        error=result.stderr or result.stdout,
                    )
                ],
                runtime_ms=result.runtime_ms,
            )

    def _build_harness(self, code: str, test_cases: list[dict], method_name: str) -> str:
        tc_json = json.dumps(test_cases)
        return f"""import json
{code}

_tc = json.loads({tc_json!r})
_results = []
for i, tc in enumerate(_tc):
    try:
        _args = tc["input"] if isinstance(tc["input"], list) else [tc["input"]]
        _actual = getattr(Solution(), "{method_name}")(*_args)
        _passed = _actual == tc["expected"]
        _results.append({{"id": i+1, "passed": _passed, "input": str(tc["input"]),
                         "expected": str(tc["expected"]), "actual": str(_actual), "error": None}})
    except Exception as e:
        _results.append({{"id": i+1, "passed": False, "input": str(tc.get("input","")),
                         "expected": str(tc.get("expected","")), "actual": "", "error": str(e)}})
print(json.dumps({{"passed": sum(r["passed"] for r in _results), "total": len(_results), "results": _results}}))
"""

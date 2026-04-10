from app.services.sandbox import SandboxService


async def test_run_code_prints_hello():
    sandbox = SandboxService()
    result = await sandbox.run_code('print("hello")')
    assert result.stdout == "hello\n"
    assert result.exit_code == 0


async def test_run_code_syntax_error_has_nonzero_exit():
    sandbox = SandboxService()
    result = await sandbox.run_code("def broken(:\n    pass")
    assert result.exit_code != 0
    assert result.stderr


async def test_run_code_infinite_loop_times_out():
    sandbox = SandboxService()
    result = await sandbox.run_code("while True:\n    pass", timeout=2)
    assert result.timed_out is True
    assert result.exit_code == -1


async def test_run_tests_all_pass():
    sandbox = SandboxService()
    code = (
        "class Solution:\n"
        "    def add(self, a: int, b: int) -> int:\n"
        "        return a + b\n"
    )
    test_cases = [
        {"input": [1, 2], "expected": 3},
        {"input": [5, 7], "expected": 12},
    ]
    result = await sandbox.run_tests(code, test_cases, "add")
    assert result.passed == 2
    assert result.failed == 0


async def test_run_tests_failing_case_reports_actual_expected():
    sandbox = SandboxService()
    code = (
        "class Solution:\n"
        "    def add(self, a: int, b: int) -> int:\n"
        "        return a - b\n"
    )
    test_cases = [{"input": [5, 2], "expected": 7}]
    result = await sandbox.run_tests(code, test_cases, "add")
    assert result.failed == 1
    assert result.results[0].expected == "7"
    assert result.results[0].actual == "3"


async def test_run_tests_runtime_error_is_captured():
    sandbox = SandboxService()
    code = (
        "class Solution:\n"
        "    def crash(self, a: int) -> int:\n"
        "        return a / 0\n"
    )
    test_cases = [{"input": [1], "expected": 0}]
    result = await sandbox.run_tests(code, test_cases, "crash")
    assert result.failed == 1
    assert result.results[0].error is not None

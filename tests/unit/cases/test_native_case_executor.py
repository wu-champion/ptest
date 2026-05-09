from __future__ import annotations

import signal
import textwrap
from pathlib import Path

from ptest.app import WorkflowService


def _create_crash_script(tmp_path: Path, behavior: str) -> Path:
    script = tmp_path / f"native_{behavior}.py"
    if behavior == "normal":
        script.write_text("print('hello')\n", encoding="utf-8")
    elif behavior == "fail":
        script.write_text("print('failing'); raise SystemExit(1)\n", encoding="utf-8")
    elif behavior == "abort":
        script.write_text(
            "import os; print('aborting'); os.abort()\n", encoding="utf-8"
        )
    elif behavior == "signal":
        script.write_text(
            "import os, signal; print('killing'); os.kill(os.getpid(), signal.SIGTERM)\n",
            encoding="utf-8",
        )
    elif behavior == "timeout":
        script.write_text("import time; time.sleep(60)\n", encoding="utf-8")
    elif behavior == "stderr":
        script.write_text(
            "import sys; sys.stdout.write('out'); sys.stderr.write('err'); raise SystemExit(0)\n",
            encoding="utf-8",
        )
    script.chmod(0o755)
    return script


def test_native_case_normal_exit_passed(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    script = _create_crash_script(tmp_path, "normal")

    service.add_case(
        "native_ok",
        {
            "type": "native",
            "name": "native_ok",
            "command": ["python3", str(script)],
        },
    )
    result = service.run_case("native_ok")
    assert result["status"] == "passed"
    assert isinstance(result["output"], dict)
    assert result["output"]["returncode"] == 0
    assert result["output"]["crash_detected"] is False
    assert result["output"]["timed_out"] is False


def test_native_case_nonzero_exit_failed(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    script = _create_crash_script(tmp_path, "fail")

    service.add_case(
        "native_fail",
        {
            "type": "native",
            "name": "native_fail",
            "command": ["python3", str(script)],
        },
    )
    result = service.run_case("native_fail")
    assert result["status"] == "failed"
    assert isinstance(result["output"], dict)
    assert result["output"]["returncode"] == 1
    assert result["output"]["crash_detected"] is False


def test_native_case_abort_records_signal(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    script = _create_crash_script(tmp_path, "abort")

    service.add_case(
        "native_abort",
        {
            "type": "native",
            "name": "native_abort",
            "command": ["python3", str(script)],
        },
    )
    result = service.run_case("native_abort")
    assert result["status"] == "failed"
    assert isinstance(result["output"], dict)
    assert result["output"]["returncode"] < 0
    assert result["output"]["crash_detected"] is True
    assert result["output"]["signal"] is not None


def test_native_case_signal_exit(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    script = _create_crash_script(tmp_path, "signal")

    service.add_case(
        "native_sigterm",
        {
            "type": "native",
            "name": "native_sigterm",
            "command": ["python3", str(script)],
        },
    )
    result = service.run_case("native_sigterm")
    assert result["status"] == "failed"
    assert isinstance(result["output"], dict)
    assert result["output"]["returncode"] == -signal.SIGTERM
    assert result["output"]["crash_detected"] is True
    assert "SIGTERM" in result["output"]["signal"]


def test_native_case_timeout(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    script = _create_crash_script(tmp_path, "timeout")

    service.add_case(
        "native_timeout",
        {
            "type": "native",
            "name": "native_timeout",
            "command": ["python3", str(script)],
            "timeout": 1,
        },
    )
    result = service.run_case("native_timeout")
    assert result["status"] == "failed"
    assert isinstance(result["output"], dict)
    assert result["output"]["timed_out"] is True
    assert result["output"]["crash_detected"] is True


def test_native_case_crash_expected_passes(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    script = _create_crash_script(tmp_path, "abort")

    service.add_case(
        "native_crash_expected",
        {
            "type": "native",
            "name": "native_crash_expected",
            "command": ["python3", str(script)],
            "crash_expected": True,
        },
    )
    result = service.run_case("native_crash_expected")
    assert result["status"] == "passed"
    assert isinstance(result["output"], dict)
    assert result["output"]["crash_detected"] is True
    assert result["output"]["crash_expected"] is True


def test_native_case_invalid_command_error(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    service.add_case(
        "native_bad_cmd",
        {
            "type": "native",
            "name": "native_bad_cmd",
            "command": "not_a_list",
        },
    )
    result = service.run_case("native_bad_cmd")
    assert result["status"] in ("failed", "error")


def test_native_case_command_not_found(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    service.add_case(
        "native_notfound",
        {
            "type": "native",
            "name": "native_notfound",
            "command": ["/nonexistent/binary"],
        },
    )
    result = service.run_case("native_notfound")
    assert result["status"] in ("failed", "error")


def test_native_case_cwd_does_not_exist(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    script = _create_crash_script(tmp_path, "normal")

    service.add_case(
        "native_bad_cwd",
        {
            "type": "native",
            "name": "native_bad_cwd",
            "command": ["python3", str(script)],
            "cwd": "/nonexistent/path",
        },
    )
    result = service.run_case("native_bad_cwd")
    assert result["status"] in ("failed", "error")


def test_native_case_cwd_working(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    script = _create_crash_script(tmp_path, "normal")

    service.add_case(
        "native_cwd",
        {
            "type": "native",
            "name": "native_cwd",
            "command": ["python3", str(script)],
            "cwd": str(tmp_path),
        },
    )
    result = service.run_case("native_cwd")
    assert result["status"] == "passed"
    assert isinstance(result["output"], dict)
    assert result["output"]["cwd"] == str(tmp_path)


def test_native_case_env_merged(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    script = tmp_path / "check_env.py"
    script.write_text(
        textwrap.dedent("""\
            import os
            val = os.environ.get("PTEST_NATIVE_CHECK", "")
            print(val)
            raise SystemExit(0 if val == "hello" else 1)
        """),
        encoding="utf-8",
    )
    script.chmod(0o755)

    service.add_case(
        "native_env",
        {
            "type": "native",
            "name": "native_env",
            "command": ["python3", str(script)],
            "env": {"PTEST_NATIVE_CHECK": "hello"},
        },
    )
    result = service.run_case("native_env")
    assert result["status"] == "passed"


def test_native_case_stdout_stderr_captured(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    script = _create_crash_script(tmp_path, "stderr")

    service.add_case(
        "native_io",
        {
            "type": "native",
            "name": "native_io",
            "command": ["python3", str(script)],
        },
    )
    result = service.run_case("native_io")
    assert result["status"] == "passed"
    assert isinstance(result["output"], dict)
    assert result["output"]["stdout_size"] > 0
    assert result["output"]["stderr_size"] > 0
    assert Path(result["output"]["stdout_ref"]).exists()
    assert Path(result["output"]["stderr_ref"]).exists()

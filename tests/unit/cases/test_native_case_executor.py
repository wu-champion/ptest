from __future__ import annotations

import signal
import sys
import textwrap
from pathlib import Path

import pytest

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
    assert "/tmp/ptest_native_" not in result.get("error_message", "")


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
    assert result["output"]["crash_detected"] is True
    assert result["output"]["signal"] is not None
    rc = result["output"]["returncode"]
    assert rc < 0 or rc >= 0xC0000000


@pytest.mark.skipif(
    sys.platform == "win32", reason="os.kill(SIGTERM) semantics differ on Windows"
)
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

    records = service.list_execution_records(case_id="native_io")
    execution_id = records[0]["execution_id"]
    artifacts = service.get_execution_artifacts(execution_id)
    np = artifacts["data"]["categories"]["native_process"]
    assert Path(tmp_path / np["stdout"]).exists()
    assert Path(tmp_path / np["stderr"]).exists()


def test_native_case_artifacts_include_native_process(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    script = _create_crash_script(tmp_path, "stderr")

    service.add_case(
        "native_art",
        {
            "type": "native",
            "name": "native_art",
            "command": ["python3", str(script)],
            "log_paths": [str(tmp_path / "no_such.log")],
            "config_paths": [str(tmp_path / "no_such.conf")],
        },
    )
    result = service.run_case("native_art")
    assert result["status"] == "passed"

    records = service.list_execution_records(case_id="native_art")
    assert len(records) >= 1
    execution_id = records[0]["execution_id"]

    artifacts = service.get_execution_artifacts(execution_id)
    assert artifacts["success"] is True
    categories = artifacts["data"].get("categories", {})
    assert "native_process" in categories
    np_cat = categories["native_process"]
    assert "native_process" in np_cat
    assert "stdout" in np_cat
    assert "stderr" in np_cat


def test_native_case_artifact_files_exist(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    script = _create_crash_script(tmp_path, "stderr")

    service.add_case(
        "native_files",
        {
            "type": "native",
            "name": "native_files",
            "command": ["python3", str(script)],
        },
    )
    result = service.run_case("native_files")
    assert result["status"] == "passed"

    records = service.list_execution_records(case_id="native_files")
    execution_id = records[0]["execution_id"]
    artifacts = service.get_execution_artifacts(execution_id)

    np_files = artifacts["data"].get("files", {})
    assert "native_process" in np_files
    assert "native_stdout" in np_files
    assert "native_stderr" in np_files

    np_path = (
        tmp_path
        / ".ptest"
        / "artifacts"
        / execution_id
        / "native_process"
        / "native_process.json"
    )
    assert np_path.exists()


def test_non_native_case_no_native_artifact(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()

    service.add_case(
        "sqlite_smoke",
        {
            "type": "database",
            "name": "sqlite_smoke",
            "db_type": "sqlite",
            "database": str(tmp_path / "test.db"),
            "query": "SELECT 1 as value",
            "expected_result": [{"value": 1}],
        },
    )
    result = service.run_case("sqlite_smoke")
    assert result["status"] == "passed"

    records = service.list_execution_records(case_id="sqlite_smoke")
    execution_id = records[0]["execution_id"]
    artifacts = service.get_execution_artifacts(execution_id)

    categories = artifacts["data"].get("categories", {})
    assert "native_process" not in categories


def test_native_case_log_config_summaries(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    script = _create_crash_script(tmp_path, "normal")

    log_file = tmp_path / "test.log"
    log_file.write_text("log content\n", encoding="utf-8")
    conf_file = tmp_path / "test.conf"
    conf_file.write_text("key=value\n", encoding="utf-8")

    service.add_case(
        "native_refs",
        {
            "type": "native",
            "name": "native_refs",
            "command": ["python3", str(script)],
            "log_paths": [str(log_file)],
            "config_paths": [str(conf_file)],
            "data_summary_paths": [str(tmp_path)],
            "env": {"PTEST_NATIVE_REFS_CHECK": "1"},
        },
    )
    result = service.run_case("native_refs")
    assert result["status"] == "passed"

    records = service.list_execution_records(case_id="native_refs")
    execution_id = records[0]["execution_id"]
    artifacts = service.get_execution_artifacts(execution_id)

    np_ref = artifacts["data"]["categories"]["native_process"]["native_process"]
    import json

    np_data = json.loads((tmp_path / np_ref).read_text(encoding="utf-8"))
    assert len(np_data["log_refs"]) == 1
    assert np_data["log_refs"][0]["exists"] is True
    assert len(np_data["config_refs"]) == 1
    assert np_data["config_refs"][0]["exists"] is True
    assert len(np_data["data_dir_summaries"]) == 1
    assert "env_keys" in np_data["framework_context"]
    assert np_data["case_id"] == "native_refs"
    assert np_data["capture_status"] == "available"


def test_native_case_core_environment_in_artifact(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    script = _create_crash_script(tmp_path, "normal")

    service.add_case(
        "native_core_env",
        {
            "type": "native",
            "name": "native_core_env",
            "command": ["python3", str(script)],
        },
    )
    result = service.run_case("native_core_env")
    assert result["status"] == "passed"

    records = service.list_execution_records(case_id="native_core_env")
    execution_id = records[0]["execution_id"]
    artifacts = service.get_execution_artifacts(execution_id)

    np_ref = artifacts["data"]["categories"]["native_process"]["native_process"]
    import json

    np_data = json.loads((tmp_path / np_ref).read_text(encoding="utf-8"))
    assert "core_environment" in np_data
    core_env = np_data["core_environment"]
    assert "platform" in core_env
    assert "core_supported" in core_env
    assert "core_enabled" in core_env
    assert "rlimit_core" in core_env
    assert "core_pattern" in core_env
    assert "dump_dir" in core_env
    assert "dump_dir_writable" in core_env
    assert "limitations" in core_env


def test_native_case_crash_capture_in_artifact(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    script = _create_crash_script(tmp_path, "normal")

    service.add_case(
        "native_crash_cap",
        {
            "type": "native",
            "name": "native_crash_cap",
            "command": ["python3", str(script)],
        },
    )
    result = service.run_case("native_crash_cap")
    assert result["status"] == "passed"

    records = service.list_execution_records(case_id="native_crash_cap")
    execution_id = records[0]["execution_id"]
    artifacts = service.get_execution_artifacts(execution_id)

    np_ref = artifacts["data"]["categories"]["native_process"]["native_process"]
    import json

    np_data = json.loads((tmp_path / np_ref).read_text(encoding="utf-8"))
    assert "crash_capture" in np_data
    cc = np_data["crash_capture"]
    assert "before" in cc
    assert "after" in cc
    assert "new_dump_refs" in cc
    assert isinstance(cc["new_dump_refs"], list)


def test_native_case_dump_watch_dirs_scanned(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    script = _create_crash_script(tmp_path, "normal")

    watch_dir = tmp_path / "custom_dumps"
    watch_dir.mkdir()

    service.add_case(
        "native_watch_dirs",
        {
            "type": "native",
            "name": "native_watch_dirs",
            "command": ["python3", str(script)],
            "dump_watch_dirs": [str(watch_dir)],
        },
    )
    result = service.run_case("native_watch_dirs")
    assert result["status"] == "passed"

    records = service.list_execution_records(case_id="native_watch_dirs")
    record_dict = records[0]
    crash_capture = record_dict.get("metadata", {}).get("crash_capture", {})
    after = crash_capture.get("after", {})
    directories = after.get("directories", [])
    assert any(str(watch_dir.resolve()) in d for d in directories)


def test_native_crash_generates_crash_dump_problem(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    script = _create_crash_script(tmp_path, "abort")

    service.add_case(
        "native_crash_problem",
        {
            "type": "native",
            "name": "native_crash_problem",
            "command": ["python3", str(script)],
        },
    )
    result = service.run_case("native_crash_problem")
    assert result["status"] == "failed"

    problems = service.list_problem_records(case_id="native_crash_problem")
    assert len(problems) >= 1
    assert any(p["problem_type"] == "crash_dump" for p in problems)

    problem_id = next(
        p["problem_id"] for p in problems if p["problem_type"] == "crash_dump"
    )
    assets = service.get_problem_assets(problem_id)
    assert assets["success"] is True
    details = assets["assets"]["details"]
    assert "process_result" in details
    assert details["process_result"]["crash_detected"] is True
    assert "core_environment" in details
    assert "platform" in details["core_environment"]


def test_native_crash_expected_also_generates_problem(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    script = _create_crash_script(tmp_path, "abort")

    service.add_case(
        "native_crash_expected_problem",
        {
            "type": "native",
            "name": "native_crash_expected_problem",
            "command": ["python3", str(script)],
            "crash_expected": True,
        },
    )
    result = service.run_case("native_crash_expected_problem")
    assert result["status"] == "passed"

    problems = service.list_problem_records(case_id="native_crash_expected_problem")
    assert len(problems) >= 1
    crash_problems = [p for p in problems if p["problem_type"] == "crash_dump"]
    assert len(crash_problems) >= 1


def test_native_crash_problem_recovery_has_site_summary(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    script = _create_crash_script(tmp_path, "abort")

    service.add_case(
        "native_crash_recovery",
        {
            "type": "native",
            "name": "native_crash_recovery",
            "command": ["python3", str(script)],
        },
    )
    result = service.run_case("native_crash_recovery")
    assert result["status"] == "failed"

    problems = service.list_problem_records(case_id="native_crash_recovery")
    crash_problems = [p for p in problems if p["problem_type"] == "crash_dump"]
    assert len(crash_problems) >= 1
    problem_id = crash_problems[0]["problem_id"]

    recovery = service.recover_problem(problem_id)
    assert recovery["success"] is True
    assert "process_result" in recovery["recovery"]
    assert "core_environment" in recovery["recovery"]
    assert "site_summary" in recovery["recovery"]
    assert recovery["recovery"]["supported"] is False
    assert recovery["recovery"]["mode"] == "crash_dump_investigation"

    site = recovery["recovery"]["site_summary"]
    assert isinstance(site.get("dump_count"), int)
    assert site.get("log_count", 0) == 0
    assert site.get("config_count", 0) == 0
    assert site.get("data_summary_count", 0) == 0
    assert "stdout_ref" in site
    assert "stderr_ref" in site


def test_native_crash_investigation_has_process_exit(tmp_path: Path) -> None:
    service = WorkflowService(tmp_path)
    service.init_environment()
    script = _create_crash_script(tmp_path, "abort")

    service.add_case(
        "native_crash_investigation",
        {
            "type": "native",
            "name": "native_crash_investigation",
            "command": ["python3", str(script)],
        },
    )
    result = service.run_case("native_crash_investigation")
    assert result["status"] == "failed"

    problems = service.list_problem_records(case_id="native_crash_investigation")
    crash_problems = [p for p in problems if p["problem_type"] == "crash_dump"]
    assert len(crash_problems) >= 1
    problem_id = crash_problems[0]["problem_id"]

    problem = service.get_problem_record(problem_id)
    investigation = problem["problem"]["investigation"]
    assert "process_exit" in investigation
    assert investigation["process_exit"]["crash_detected"] is True
    assert "core_environment" in investigation

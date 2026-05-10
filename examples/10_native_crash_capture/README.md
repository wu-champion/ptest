# Example 10: Native Crash Capture

Demonstrates how ptest captures real product process crash scenes through the `native` case type.

## What This Example Covers

- Running a real native process that crashes (abort / signal / nonzero exit)
- Capturing process exit code, signal, stdout/stderr as execution artifacts
- Probing core environment (rlimit, core_pattern, dump directory)
- Scanning for dump/core files before and after execution
- Generating `crash_dump` problem with process result and core environment
- Viewing problem assets and recovery plan

## Files

| File | Purpose |
|------|---------|
| `crash_program.py` | Minimal crash program (abort, signal, nonzero exit, normal) |
| `native_abort_case.json` | Case definition for running the crash program |
| `product_runner_case.json` | Example mapping for a product test runner (pytest, ASAN, etc.) |

## Quick Start

```bash
cd examples/10_native_crash_capture

# Add and run the native crash case
ptest case add native_abort_demo --file native_abort_case.json
ptest case run native_abort_demo

# View the execution artifacts (includes native_process category)
ptest execution artifacts <execution_id>

# List crash_dump problems
ptest problem list --type crash_dump

# View problem assets (process_result, core_environment, dump_refs)
ptest problem assets <problem_id>

# View recovery plan (investigation-only, no auto-recovery)
ptest problem recover <problem_id>
```

## Case Definition Fields

### Required

- `type`: must be `"native"`
- `name`: case identifier
- `command`: `list[str]` — the command to execute (no shell string, no `shell=True`)

### Optional

- `cwd`: working directory (must exist if provided)
- `env`: environment variables merged into subprocess environment
- `timeout`: seconds before forced termination
- `expected_exit_code`: default `0`
- `crash_expected`: `true` if the test expects a crash (case passes on crash)
- `dump_watch_dirs`: additional directories to scan for core/dump files
- `log_paths`: log file/directory references (summarized, not full content)
- `config_paths`: config file references (summarized)
- `data_summary_paths`: data directory references (summary only)
- `object_name`: associate with a managed object

## Product Runner Mapping

When wrapping a product test runner (pytest, ASAN, Valgrind, shell script, or C crash program),
map the fields as follows:

```json
{
  "type": "native",
  "name": "product_stability_test",
  "command": ["pytest", "--config=demo.yaml", "cases/crash/test_stability.py"],
  "cwd": "/workspace/product/test",
  "env": {
    "TEST_ROOT": "/workspace/product/test",
    "ASAN_OPTIONS": "detect_leaks=0",
    "LD_LIBRARY_PATH": "/workspace/product/lib"
  },
  "timeout": 600,
  "dump_watch_dirs": ["/tmp", "/var/lib/systemd/coredump"],
  "log_paths": ["/workspace/product/test/run", "/var/log/product"],
  "config_paths": ["/workspace/product/test/env/demo.yaml"],
  "data_summary_paths": ["/var/lib/product"]
}
```

## Core Environment Behavior

Core dump generation depends on the operating system configuration:

| Setting | Check | Effect |
|---------|-------|--------|
| `ulimit -c` (soft) | `resource.getrlimit(RLIMIT_CORE)` | `0` = core disabled |
| `ulimit -c` (hard) | `resource.getrlimit(RLIMIT_CORE)` | `0` = hard limit blocks core |
| `core_pattern` | `/proc/sys/kernel/core_pattern` | `\|handler` = pipe to handler |
| dump directory | write test | not writable = core lost |

ptest records all of these in `core_environment` even when core is not generated.
The `limitations` array explains why core may not be available.

## Artifacts Produced

Each native case execution generates:

- `native_process/native_process.json` — full process result + core_environment + crash_capture
- `native_process/stdout.txt` — captured stdout
- `native_process/stderr.txt` — captured stderr
- `context/environment.json` — environment snapshot
- `result/result.json` — execution result
- `indexes/artifact_index.json` — manifest with categories

## Problem Generation

A `crash_dump` problem is generated when:

1. `returncode < 0` (signal kill)
2. `timed_out = true` and process was forcefully terminated
3. `crash_detected = true` (abort, signal, etc.)
4. New dump/core files found after execution
5. `crash_expected = true` and crash scene was captured

The problem includes:

- `process_result` — command, returncode, signal, timed_out, crash_detected
- `core_environment` — platform, core_enabled, rlimit, core_pattern, limitations
- `dump_refs` — discovered core/dump files
- `native_case` — stdout/stderr references

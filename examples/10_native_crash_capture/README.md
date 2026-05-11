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

## Dump Summary (P5-B)

When `dump_paths` or auto-discovered dump files are present, ptest generates a lightweight summary for each ref:

- **file_type**: `elf_core`, `minidump`, `archive`, `text_dump`, or `unknown` (detected by magic bytes or extension)
- **hash_sha256_prefix**: first 16 hex chars of sha256 (streams up to 16 MB)
- **warnings**: `empty_file`, `file_missing`, `permission_denied`, `archive_probe_failed`, etc.

For archive files (`.zip`, `.tar`, `.tar.gz`, `.tgz`), ptest reads the directory only (no extraction) and reports:

- `entry_count`, `sample_entries` (up to 20), `total_uncompressed_size`, `truncated`

A `dump_summary` aggregate is included in `problem assets.details`, `problem show` investigation, and `problem recover`:

```json
{
  "dump_summary": {
    "total_count": 2,
    "available_count": 1,
    "unavailable_count": 1,
    "types": {"elf_core": 1, "unknown": 1},
    "has_archive": false,
    "warnings": ["file_missing"]
  }
}
```

ptest does **not** parse core contents, symbolize stacks, or extract archives. The summary is purely metadata for deciding whether to continue investigation.

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

## Managed Object Crash Linkage (P5-D)

When a native case includes `object_name`, the crash problem is linked to the managed object:

- `crash_target.object_name` uses the case `object_name` (falls back to `service_name` for backward compatibility)
- `object_summary` reports whether the object was found, its type, status, and installation state
- `next_actions` include object-specific investigation entries:
  - `inspect_object_status` — check the object after the crash
  - `inspect_execution_object_artifacts` — review captured artifacts
  - `verify_object_binding` — when object is not found
- `problem assets`, `problem show` (investigation), and `problem recover` all include `object_summary`

Example case with object linkage:

```json
{
  "type": "native",
  "name": "product_crash_test",
  "command": ["/opt/product/bin/test_runner", "--suite=stability"],
  "object_name": "product_service",
  "timeout": 300,
  "dump_watch_dirs": ["/tmp", "/var/lib/systemd/coredump"]
}
```

When `object_name` is absent, the behavior is identical to P5-A/P5-B (no object linkage).

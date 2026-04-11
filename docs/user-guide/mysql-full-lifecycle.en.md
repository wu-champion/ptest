# MySQL Full Lifecycle Walkthrough

[中文](./mysql-full-lifecycle.md) | [English](./mysql-full-lifecycle.en.md)

This is not meant to be a one-shot automation snippet.

It is written in the way many test engineers actually work:

- prepare a workspace
- install the product under test
- start it and confirm status
- run test steps in sequence
- inspect executions and preserved problems
- stop, uninstall, and clean up when finished

## What this example validates

This walkthrough validates two things at the same time.

First, it validates that MySQL can be managed by `ptest` as a real product object through:

`install -> start -> use -> stop -> uninstall`

Second, it validates that `ptest` itself can provide:

- managed workspace isolation
- object lifecycle management
- execution and problem recording
- cleanup after stop and uninstall
- no persistent workspace pollution outside the managed boundary

## Current runtime model

The current MySQL example runs on:

- a managed workspace
- `host` runtime backend

This means:

- directories, configs, logs, data, and dependency assets are managed by `ptest`
- the real `mysqld` process still depends on the host environment for process startup and TCP port binding

So this example does **not** claim that any restricted sandbox can run a real database service.

The environment still needs to allow:

- real process startup
- local TCP port binding
- loading managed shared-library dependencies

## Prerequisites

### 1. MySQL package asset

Current example target:

- `MySQL Community Server 8.4.8 LTS`
- `Ubuntu Linux 24.04 (x86, 64-bit)`
- package:
  - `mysql-server_8.4.8-1ubuntu24.04_amd64.deb-bundle.tar`

Suggested local asset path:

```text
~/.ptest/assets/mysql/8.4.8/mysql-server_8.4.8-1ubuntu24.04_amd64.deb-bundle.tar
```

### 2. Dependency assets

The current real smoke path uses dependency assets such as:

- `libaio1t64`
- `libnuma1`

Suggested location:

```text
~/.ptest/assets/mysql/8.4.8/deps/
```

### 3. Workspace path

Use a simple managed workspace, for example:

```text
~/ptest/mysql-demo
```

### 4. Command mode

This guide assumes `ptestx` is already installed and you can run:

```bash
ptest --version
```

If you are running from the source repository instead, replace `ptest` with:

```bash
uv run ptest
```

## Step-by-step workflow

### Step 1: Initialize the workspace

```bash
ptest init --path ~/ptest/mysql-demo
cd ~/ptest/mysql-demo
ptest env status
```

Typical successful output:

```text
Environment status: active
Workspace: ~/ptest/mysql-demo
Objects: 0
Cases: 0
```

### Step 2: Install the MySQL object

```bash
ptest obj install mysql mysql_demo \
  --package-path ~/.ptest/assets/mysql/8.4.8/mysql-server_8.4.8-1ubuntu24.04_amd64.deb-bundle.tar \
  --dependency-asset ~/.ptest/assets/mysql/8.4.8/deps/libaio1t64_xxx_amd64.deb \
  --dependency-asset ~/.ptest/assets/mysql/8.4.8/deps/libnuma1_xxx_amd64.deb \
  --port 13319
```

Then check status:

```bash
ptest obj status mysql_demo
```

Typical result:

```text
Object: mysql_demo
Type: mysql
Status: installed
Port: 13319
Managed root: ~/ptest/mysql-demo/.ptest/managed_objects/mysql_demo
```

### Step 3: Start the object

```bash
ptest obj start mysql_demo
ptest obj status mysql_demo
```

Typical result:

```text
Object: mysql_demo
Status: running
Port: 13319
runtime backend: host
health check: passed
```

### Step 4: Prepare a CRUD case definition

Create a file such as:

```text
./mysql_crud_case.json
```

Content:

```json
{
  "type": "database",
  "object_name": "mysql_demo",
  "operations": [
    {
      "name": "create_database",
      "query": "CREATE DATABASE IF NOT EXISTS ptest_mysql_demo"
    },
    {
      "name": "use_database",
      "query": "USE ptest_mysql_demo"
    },
    {
      "name": "create_table",
      "query": "CREATE TABLE IF NOT EXISTS crud_items (id INT PRIMARY KEY, name VARCHAR(32))"
    },
    {
      "name": "insert",
      "query": "INSERT INTO crud_items VALUES (1, 'alpha')",
      "expected_result": {"count": 1}
    },
    {
      "name": "select_after_insert",
      "query": "SELECT id, name FROM crud_items",
      "expected_result": [{"id": 1, "name": "alpha"}]
    },
    {
      "name": "update",
      "query": "UPDATE crud_items SET name = 'beta' WHERE id = 1",
      "expected_result": {"count": 1}
    },
    {
      "name": "select_after_update",
      "query": "SELECT id, name FROM crud_items",
      "expected_result": [{"id": 1, "name": "beta"}]
    },
    {
      "name": "delete",
      "query": "DELETE FROM crud_items WHERE id = 1",
      "expected_result": {"count": 1}
    },
    {
      "name": "select_after_delete",
      "query": "SELECT COUNT(*) AS count FROM crud_items",
      "expected_result": {"count": 0}
    }
  ]
}
```

The database flow is explicit now:

- create database
- switch into database
- create table
- run CRUD

That means the framework no longer silently creates a business database for the case.

### Step 5: Add the case

```bash
ptest case add mysql_crud_case --file ./mysql_crud_case.json
```

### Step 6: Run the case

```bash
ptest case run mysql_crud_case
```

Typical result:

```text
Case: mysql_crud_case
Status: passed
execution_id: execution_xxxxxxxx
```

### Step 7: Inspect execution records

```bash
ptest execution list --case-id mysql_crud_case
ptest execution artifacts <execution_id>
```

### Step 8: Add one intentionally failing case

Create:

```text
./mysql_crud_case_fail.json
```

Content:

```json
{
  "type": "database",
  "object_name": "mysql_demo",
  "operations": [
    {
      "name": "select_wrong_expectation",
      "query": "SELECT COUNT(*) AS count FROM crud_items",
      "expected_result": {"count": 99}
    }
  ]
}
```

Run it:

```bash
ptest case add mysql_crud_case_fail --file ./mysql_crud_case_fail.json
ptest case run mysql_crud_case_fail
```

### Step 9: Inspect preserved problems

```bash
ptest problem list
ptest problem show <problem_id>
ptest problem assets <problem_id>
ptest problem recover <problem_id>
```

### Step 10: If the object enters a preserved-failure state, use clear / reset

Current first-pass preserved states include:

- `install_failed_preserved`
- `start_failed_preserved`

Check status:

```bash
ptest obj status mysql_demo
```

You may see output like:

```text
Object: mysql_demo
Status: start_failed_preserved
Available actions: clear, reset
failure_state.phase: start
```

Available commands:

```bash
ptest obj clear mysql_demo
ptest obj reset mysql_demo
```

Difference:

- `clear`
  - clears the preserved failure scene
- `reset`
  - resets the whole object back to its initial state

Current first-pass behavior:

- `install_failed_preserved`
  - `clear` removes the broken object
- `start_failed_preserved`
  - `clear` returns the object to `installed`
- `clear` is rejected for normal states

### Step 11: Stop the object

```bash
ptest obj stop mysql_demo
```

### Step 12: Uninstall the object

```bash
ptest obj uninstall mysql_demo
```

### Step 13: Generate a report

```bash
ptest report generate --format json
```

or:

```bash
ptest report generate --format html
```

### Step 14: Destroy the workspace if you want a full cleanup

```bash
cd ..
ptest env destroy --path ~/ptest/mysql-demo
```

This remains intentionally explicit because `env destroy` is a workspace lifecycle cleanup action.
It does not silently fall back to the active workspace.

## Script shortcut

If you only want a quick validation, you can still use:

- [`scripts/mysql_full_lifecycle_scenario.py`](../../scripts/mysql_full_lifecycle_scenario.py)

## Common issues

### Missing shared libraries

Usually means dependency assets were not passed in with `--dependency-asset`.

### `Operation not permitted`

Usually means the current execution environment does not allow running a real service process or binding the required port.

### Port conflict

Pass an explicit `--port` to avoid conflicts with existing host services.

## About `--path` in daily use

For scripts, CI, or multi-workspace automation, explicit `--path` is still the recommended form.

For single-workspace interactive use, the smoother flow is usually:

1. `ptest init --path ~/ptest/mysql-demo`
2. `ptest workspace status`
3. optionally `cd ~/ptest/mysql-demo`
4. continue with `ptest obj ...`, `ptest case ...`, `ptest execution ...`, or `ptest exec ...`

# ptest

[中文](./README.md) | [English](./README.en.md)

`ptest` is not only about “running a test”.

It is aimed at the parts of testing work that usually get scattered across scripts, notes, and ad hoc cleanup:

- bringing a real service up in a managed workspace
- keeping execution records, logs, and object state together
- preserving useful failure context instead of losing it after a failed run
- cleaning the environment back down without leaving a mess behind

In practice, the pain is often not “how do I write one case”, but:

**how do I prepare a real product, test it, keep the failure scene, and then cleanly recover the machine afterwards?**

## What it can do today

`ptest` already has a fairly complete testing backbone:

- initialize a managed workspace
- install and manage test objects
- bind cases to managed objects and execute them
- generate execution records, reports, and problem records
- preserve useful context on failure
- cleanly stop and uninstall managed objects

It is better understood as a **testing lifecycle framework**, not just a command runner.

## One naming detail first

You will see two names:

- project name: `ptest`
- PyPI package name: `ptestx`

That is intentional:

- the product and repository are still called `ptest`
- the `ptest` name on PyPI is already taken
- so the published package is `ptestx`
- after installation, the CLI command is still:
  - `ptest`

So the normal usage is:

```bash
pip install ptestx
ptest --version
```

## A real example

To keep this concrete, the repository includes a repeatable real example:

**MySQL Full Lifecycle Walkthrough**

It walks through:

`install -> start -> use -> stop -> uninstall`

This validates both sides of the framework:

- MySQL can be treated as a managed product object
- `ptest` can actually manage lifecycle, records, and cleanup around it

The current MySQL example is built on:

- `MySQL Community Server 8.4.8 LTS`
- local package assets
- a managed workspace
- `host` runtime backend

The database testing flow in this example is also explicit:

- create a database
- switch into that database
- create a table
- run CRUD

That keeps the example aligned with how test engineers usually validate a real database product.

## Quick look

If you already installed `ptestx`, you can use the `ptest` command directly.

```bash
ptest init --path ~/ptest/mysql-demo
cd ~/ptest/mysql-demo

ptest obj install mysql mysql_demo \
  --package-path ~/.ptest/assets/mysql/8.4.8/mysql-server_8.4.8-1ubuntu24.04_amd64.deb-bundle.tar \
  --dependency-asset ~/.ptest/assets/mysql/8.4.8/deps/libaio1t64_xxx_amd64.deb \
  --dependency-asset ~/.ptest/assets/mysql/8.4.8/deps/libnuma1_xxx_amd64.deb \
  --port 13319

ptest obj start mysql_demo
ptest case run mysql_crud_case
```

This is intentionally shown as a step-by-step flow, because that is how many test engineers actually work:

- create the workspace
- install the object
- start it
- run cases in stages
- inspect results
- decide when to stop and uninstall

If you want the full walkthrough, start here:

- [MySQL 全生命周期实践](./docs/user-guide/mysql-full-lifecycle.md)
- [MySQL Full Lifecycle Walkthrough](./docs/user-guide/mysql-full-lifecycle.en.md)

## Current boundary

To keep expectations honest:

- `ptest` already handles managed workspace isolation and object lifecycle well
- for lightweight objects, that is often enough
- for a real service such as MySQL, the current example runs on a `host` runtime backend

That means the execution environment still needs to allow:

- real process startup
- local TCP port binding
- dynamic library loading

So the current version does **not** claim “fully isolated real-service execution in any restricted sandbox”.

## Where to start

Recommended order:

1. [Quick Start](./docs/user-guide/basic-usage.md)
2. [MySQL 全生命周期实践](./docs/user-guide/mysql-full-lifecycle.md)
3. [MySQL Full Lifecycle Walkthrough](./docs/user-guide/mysql-full-lifecycle.en.md)
4. [Python API Guide](./docs/api/python-api-guide.md)

## Install

The PyPI package name is `ptestx`, while the CLI command remains `ptest`:

```bash
pip install ptestx
ptest --version
```

If you are working inside the source repository, this is usually more convenient:

```bash
uv sync
uv run ptest --version
```

---

`ptest` is not only trying to help you finish a test run.  
It is trying to help you manage the object, keep the failure scene, and get back to a usable state afterwards.

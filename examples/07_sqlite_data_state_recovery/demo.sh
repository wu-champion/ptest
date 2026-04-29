#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PREPARE_SCRIPT="${SCRIPT_DIR}/scripts/prepare_sqlite_state_demo.py"

AUTO_CLEANUP="ask"

for arg in "$@"; do
    case "$arg" in
        --cleanup)
            AUTO_CLEANUP="yes"
            ;;
        --keep-workspace)
            AUTO_CLEANUP="no"
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: bash examples/07_sqlite_data_state_recovery/demo.sh [--cleanup|--keep-workspace]"
            exit 1
            ;;
    esac
done

if [ -x "${PROJECT_ROOT}/.venv/bin/ptest" ]; then
    PTEST_CMD=("${PROJECT_ROOT}/.venv/bin/ptest")
elif command -v ptest >/dev/null 2>&1; then
    PTEST_CMD=(ptest)
elif command -v uv >/dev/null 2>&1 && [ -f "${PROJECT_ROOT}/pyproject.toml" ]; then
    PTEST_CMD=(uv run ptest)
else
    echo "ptest command not found. Install dependencies or create .venv first."
    exit 1
fi

WORKSPACE="$(mktemp -d /tmp/ptest-data-state-XXXXXX)"
export HOME="${WORKSPACE}/home"
mkdir -p "${HOME}"

cleanup_workspace() {
    echo "Cleaning up workspace..."
    "${PTEST_CMD[@]}" env destroy --path "${WORKSPACE}" >/dev/null 2>&1 || true
    rm -rf "${WORKSPACE}"
    echo "Workspace cleanup finished"
}

problem_id_for_case() {
    local case_id="$1"
    local output
    output="$("${PTEST_CMD[@]}" problem list --case-id "${case_id}" --path "${WORKSPACE}")"
    python3 -c 'import json,sys; data=json.load(sys.stdin); print(data["problems"][0]["problem_id"])' <<<"${output}"
}

echo "======================================"
echo "ptest sqlite data_state recovery demo"
echo "workspace: ${WORKSPACE}"
echo "======================================"
echo ""

cd "${PROJECT_ROOT}"

echo "[1/7] Initialize workspace"
"${PTEST_CMD[@]}" init --path "${WORKSPACE}"
echo ""

echo "[2/7] Prepare SQLite database and generated cases"
python3 "${PREPARE_SCRIPT}" --workspace "${WORKSPACE}"
echo ""

echo "[3/7] Import two data_state validation cases"
"${PTEST_CMD[@]}" case add sqlite_state_mismatch --file "${WORKSPACE}/generated_cases/01_order_state_mismatch.json" --path "${WORKSPACE}"
"${PTEST_CMD[@]}" case add sqlite_missing_order --file "${WORKSPACE}/generated_cases/02_missing_order.json" --path "${WORKSPACE}"
"${PTEST_CMD[@]}" case list --path "${WORKSPACE}"
echo ""

echo "[4/7] Trigger value_mismatch"
"${PTEST_CMD[@]}" case run sqlite_state_mismatch --path "${WORKSPACE}" || true
STATE_PROBLEM_ID="$(problem_id_for_case sqlite_state_mismatch)"
echo "value_mismatch problem_id: ${STATE_PROBLEM_ID}"
"${PTEST_CMD[@]}" problem assets "${STATE_PROBLEM_ID}" --path "${WORKSPACE}"
"${PTEST_CMD[@]}" problem recover "${STATE_PROBLEM_ID}" --path "${WORKSPACE}"
echo ""

echo "[5/7] Trigger missing_rows"
"${PTEST_CMD[@]}" case run sqlite_missing_order --path "${WORKSPACE}" || true
MISSING_PROBLEM_ID="$(problem_id_for_case sqlite_missing_order)"
echo "missing_rows problem_id: ${MISSING_PROBLEM_ID}"
"${PTEST_CMD[@]}" problem assets "${MISSING_PROBLEM_ID}" --path "${WORKSPACE}"
"${PTEST_CMD[@]}" problem recover "${MISSING_PROBLEM_ID}" --path "${WORKSPACE}"
echo ""

echo "[6/7] Inspect unified investigation summary"
"${PTEST_CMD[@]}" problem show "${STATE_PROBLEM_ID}" --path "${WORKSPACE}"
echo ""

echo "[7/7] Review the SQLite database state"
python3 - <<'PY' "${WORKSPACE}/orders.db"
from __future__ import annotations

import json
import sqlite3
import sys

db_path = sys.argv[1]
conn = sqlite3.connect(db_path)
try:
    conn.row_factory = sqlite3.Row
    rows = [dict(row) for row in conn.execute("SELECT id, state, owner FROM orders ORDER BY id")]
finally:
    conn.close()
print(json.dumps({"orders": rows}, indent=2, ensure_ascii=False))
PY
echo ""

case "${AUTO_CLEANUP}" in
    yes)
        cleanup_workspace
        ;;
    no)
        echo "Workspace kept at: ${WORKSPACE}"
        ;;
    ask)
        if [ -t 0 ]; then
            read -r -p "Clean up the workspace now? (y/N) " reply
            if [[ "${reply}" == "y" || "${reply}" == "Y" ]]; then
                cleanup_workspace
            else
                echo "Workspace kept at: ${WORKSPACE}"
            fi
        else
            echo "Non-interactive shell detected; workspace kept at: ${WORKSPACE}"
        fi
        ;;
esac

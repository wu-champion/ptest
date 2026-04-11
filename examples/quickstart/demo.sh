#!/usr/bin/env bash
# ptest quickstart demo aligned with the current mainline workflow

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

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
            echo "Usage: bash examples/quickstart/demo.sh [--cleanup|--keep-workspace]"
            exit 1
            ;;
    esac
done

if command -v uv >/dev/null 2>&1 && [ -f "${PROJECT_ROOT}/pyproject.toml" ]; then
    PTEST_CMD=(uv run ptest)
else
    PTEST_CMD=(ptest)
fi

WORKSPACE="$(mktemp -d /tmp/ptest-quickstart-XXXXXX)"
DB_PATH="${WORKSPACE}/demo.db"
CASE_JSON='{"type":"database","db_type":"sqlite","database":"'"${DB_PATH}"'","query":"SELECT 1 as value","expected_result":[{"value":1}]}'

echo "======================================"
echo "ptest quickstart demo"
echo "workspace: ${WORKSPACE}"
echo "======================================"
echo ""

cd "${PROJECT_ROOT}"

echo "[1/8] Initialize workspace"
"${PTEST_CMD[@]}" init --path "${WORKSPACE}"
"${PTEST_CMD[@]}" workspace status
echo ""

echo "[2/8] Install SQLite test object"
"${PTEST_CMD[@]}" obj install db demo_db --database "${DB_PATH}" --driver sqlite
echo ""

echo "[3/8] Start object"
"${PTEST_CMD[@]}" obj start demo_db
"${PTEST_CMD[@]}" obj status demo_db
echo ""

echo "[4/8] Add test case"
"${PTEST_CMD[@]}" case add sqlite_smoke --data "${CASE_JSON}"
"${PTEST_CMD[@]}" case list
echo ""

echo "[5/8] Run test case"
"${PTEST_CMD[@]}" case run sqlite_smoke
echo ""

echo "[6/8] Inspect execution records"
"${PTEST_CMD[@]}" exec list
echo ""

echo "[7/8] Generate HTML report"
"${PTEST_CMD[@]}" report generate --format html
echo ""

echo "[8/8] Show workspace summary"
"${PTEST_CMD[@]}" status
echo ""

cleanup_workspace() {
    echo "Cleaning up workspace..."
    "${PTEST_CMD[@]}" env destroy --path "${WORKSPACE}" || true
    echo "Workspace cleanup finished: ${WORKSPACE}"
}

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

#!/usr/bin/env bash

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
            echo "Usage: bash examples/09_crash_dump_preservation/demo.sh [--cleanup|--keep-workspace]"
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

WORKSPACE="$(mktemp -d /tmp/ptest-crash-dump-XXXXXX)"
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

FREE_PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
DUMP_FILE="${WORKSPACE}/artifacts/demo_service.core"
CASE_FILE="${WORKSPACE}/crash_dump_case.json"

cat > "${CASE_FILE}" <<JSON
{
  "type": "service",
  "service_name": "demo_crash_service",
  "check_type": "port",
  "host": "127.0.0.1",
  "port": ${FREE_PORT},
  "timeout": 1,
  "expected_runtime_state": "running",
  "dump_paths": ["${DUMP_FILE}"]
}
JSON

echo "=========================================="
echo "ptest crash_dump preservation demo"
echo "workspace: ${WORKSPACE}"
echo "service endpoint: 127.0.0.1:${FREE_PORT}"
echo "dump file: ${DUMP_FILE}"
echo "=========================================="
echo ""

cd "${PROJECT_ROOT}"

echo "[1/7] Initialize workspace"
"${PTEST_CMD[@]}" init --path "${WORKSPACE}"
echo ""

echo "[2/7] Start one-shot crash service"
python3 "${PROJECT_ROOT}/examples/09_crash_dump_preservation/service/crash_once_server.py" \
  127.0.0.1 "${FREE_PORT}" "${DUMP_FILE}" >/dev/null 2>&1 &
SERVER_PID=$!
sleep 0.3
echo ""

echo "[3/7] Import crash_dump validation case"
"${PTEST_CMD[@]}" case add service_crash_dump_check --file "${CASE_FILE}" --path "${WORKSPACE}"
echo ""

echo "[4/7] Trigger one-shot crash"
python3 -c "import socket; s=socket.create_connection(('127.0.0.1', ${FREE_PORT}), timeout=1); s.close()"
wait "${SERVER_PID}" || true
test -f "${DUMP_FILE}"
echo "dump generated: ${DUMP_FILE}"
echo ""

echo "[5/7] Run case and create crash_dump problem"
"${PTEST_CMD[@]}" case run service_crash_dump_check --path "${WORKSPACE}" || true
PROBLEM_ID="$(problem_id_for_case service_crash_dump_check)"
echo "crash_dump problem_id: ${PROBLEM_ID}"
echo ""

echo "[6/7] Inspect preserved crash assets"
"${PTEST_CMD[@]}" problem assets "${PROBLEM_ID}" --path "${WORKSPACE}"
echo ""

echo "[7/7] Inspect structured crash recovery plan"
"${PTEST_CMD[@]}" problem recover "${PROBLEM_ID}" --path "${WORKSPACE}"
echo ""

echo "[8/8] Inspect unified investigation summary"
"${PTEST_CMD[@]}" problem show "${PROBLEM_ID}" --path "${WORKSPACE}"
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

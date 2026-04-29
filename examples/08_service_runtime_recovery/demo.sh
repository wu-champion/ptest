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
            echo "Usage: bash examples/08_service_runtime_recovery/demo.sh [--cleanup|--keep-workspace]"
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

WORKSPACE="$(mktemp -d /tmp/ptest-service-runtime-XXXXXX)"
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
CASE_FILE="${WORKSPACE}/service_runtime_case.json"

cat > "${CASE_FILE}" <<JSON
{
  "type": "service",
  "service_name": "demo_runtime_service",
  "check_type": "port",
  "host": "127.0.0.1",
  "port": ${FREE_PORT},
  "timeout": 1
}
JSON

echo "=========================================="
echo "ptest service_runtime recovery demo"
echo "workspace: ${WORKSPACE}"
echo "unreachable endpoint: 127.0.0.1:${FREE_PORT}"
echo "=========================================="
echo ""

cd "${PROJECT_ROOT}"

echo "[1/6] Initialize workspace"
"${PTEST_CMD[@]}" init --path "${WORKSPACE}"
echo ""

echo "[2/6] Import service runtime validation case"
"${PTEST_CMD[@]}" case add service_runtime_port_unreachable --file "${CASE_FILE}" --path "${WORKSPACE}"
"${PTEST_CMD[@]}" case list --path "${WORKSPACE}"
echo ""

echo "[3/6] Trigger service runtime failure"
"${PTEST_CMD[@]}" case run service_runtime_port_unreachable --path "${WORKSPACE}" || true
PROBLEM_ID="$(problem_id_for_case service_runtime_port_unreachable)"
echo "service_runtime problem_id: ${PROBLEM_ID}"
echo ""

echo "[4/6] Inspect preserved runtime assets"
"${PTEST_CMD[@]}" problem assets "${PROBLEM_ID}" --path "${WORKSPACE}"
echo ""

echo "[5/6] Inspect structured recovery plan"
"${PTEST_CMD[@]}" problem recover "${PROBLEM_ID}" --path "${WORKSPACE}"
echo ""

echo "[6/6] Inspect unified investigation summary"
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

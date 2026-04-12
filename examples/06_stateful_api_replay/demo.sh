#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${WORKSPACE:-/tmp/ptest-stateful-api-replay}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-18090}"
SERVER_LOG="${SERVER_LOG:-/tmp/ptest-stateful-api-replay-server.log}"

python3 "${SCRIPT_DIR}/service/stateful_api_server.py" --host "${HOST}" --port "${PORT}" >"${SERVER_LOG}" 2>&1 &
SERVER_PID=$!

cleanup() {
  if kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
    kill "${SERVER_PID}" >/dev/null 2>&1 || true
    wait "${SERVER_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

sleep 1

rm -rf "${WORKSPACE}"

ptest init --path "${WORKSPACE}"

ptest case add direct_body_mismatch --file "${SCRIPT_DIR}/cases/01_direct_body_mismatch.json" --path "${WORKSPACE}"
ptest case add enable_hidden_failure --file "${SCRIPT_DIR}/cases/02_enable_hidden_failure.json" --path "${WORKSPACE}"
ptest case add orders_after_hidden_state --file "${SCRIPT_DIR}/cases/03_orders_after_hidden_state.json" --path "${WORKSPACE}"

ptest case run direct_body_mismatch --path "${WORKSPACE}" || true
ptest problem list --case-id direct_body_mismatch --path "${WORKSPACE}"

ptest case run enable_hidden_failure --path "${WORKSPACE}"
ptest case run orders_after_hidden_state --path "${WORKSPACE}" || true
ptest problem list --case-id orders_after_hidden_state --path "${WORKSPACE}"

echo
echo "Server log: ${SERVER_LOG}"
echo "Workspace: ${WORKSPACE}"
echo "Use 'ptest problem assets <problem_id> --path ${WORKSPACE}' to inspect reproduction summary."
echo "Use 'ptest problem replay <problem_id> --path ${WORKSPACE}' to inspect replay boundary."

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
WORKSPACE="${WORKSPACE:-/tmp/ptest-stateful-api-replay}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-18090}"
SERVER_LOG="${SERVER_LOG:-/tmp/ptest-stateful-api-replay-server.log}"

if command -v ptest >/dev/null 2>&1; then
  PTEST_CMD=(ptest)
elif [[ -x "${REPO_ROOT}/.venv/bin/ptest" ]]; then
  PTEST_CMD=("${REPO_ROOT}/.venv/bin/ptest")
elif command -v uv >/dev/null 2>&1; then
  PTEST_CMD=(uv run ptest)
else
  echo "Unable to find a runnable ptest command." >&2
  echo "Install ptest or create the project .venv first." >&2
  exit 1
fi

python3 "${SCRIPT_DIR}/service/stateful_api_server.py" --host "${HOST}" --port "${PORT}" >"${SERVER_LOG}" 2>&1 &
SERVER_PID=$!

cleanup() {
  if kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
    kill "${SERVER_PID}" >/dev/null 2>&1 || true
    wait "${SERVER_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

for _ in $(seq 1 20); do
  if python3 -c "import urllib.request; urllib.request.urlopen('http://${HOST}:${PORT}/state/check', timeout=0.5).read()" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

if ! python3 -c "import urllib.request; urllib.request.urlopen('http://${HOST}:${PORT}/state/check', timeout=0.5).read()" >/dev/null 2>&1; then
  echo "Stateful API service did not become ready." >&2
  exit 1
fi

rm -rf "${WORKSPACE}"

"${PTEST_CMD[@]}" init --path "${WORKSPACE}"

"${PTEST_CMD[@]}" case add direct_body_mismatch --file "${SCRIPT_DIR}/cases/01_direct_body_mismatch.json" --path "${WORKSPACE}"
"${PTEST_CMD[@]}" case add enable_hidden_failure --file "${SCRIPT_DIR}/cases/02_enable_hidden_failure.json" --path "${WORKSPACE}"
"${PTEST_CMD[@]}" case add orders_after_hidden_state --file "${SCRIPT_DIR}/cases/03_orders_after_hidden_state.json" --path "${WORKSPACE}"

"${PTEST_CMD[@]}" case run direct_body_mismatch --path "${WORKSPACE}" || true
"${PTEST_CMD[@]}" problem list --case-id direct_body_mismatch --path "${WORKSPACE}"

"${PTEST_CMD[@]}" case run enable_hidden_failure --path "${WORKSPACE}"
"${PTEST_CMD[@]}" case run orders_after_hidden_state --path "${WORKSPACE}" || true
"${PTEST_CMD[@]}" problem list --case-id orders_after_hidden_state --path "${WORKSPACE}"

echo
echo "Server log: ${SERVER_LOG}"
echo "Workspace: ${WORKSPACE}"
echo "Use 'ptest problem assets <problem_id> --path ${WORKSPACE}' to inspect reproduction summary."
echo "Use 'ptest problem replay <problem_id> --path ${WORKSPACE}' to inspect replay boundary."

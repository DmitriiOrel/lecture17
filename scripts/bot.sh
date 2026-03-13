#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-shadow-once}"
shift || true

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="${PROJECT_DIR}/run_trade_signal.py"
VENV_PYTHON="${PROJECT_DIR}/venv/bin/python"

CONFIG="config/micro_near_v1_1m.json"
MODEL_PATH="models/near_basis_qlearning.json"
ENV_FILE=".runtime/kucoin.env"
EPISODES="80"
START=""
END=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2 ;;
    --model-path) MODEL_PATH="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --episodes) EPISODES="$2"; shift 2 ;;
    --start) START="$2"; shift 2 ;;
    --end) END="$2"; shift 2 ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

run_checked() {
  echo "> $*"
  "$@"
}

ensure_venv_python() {
  if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "venv python not found: $VENV_PYTHON. Run: ./scripts/bot.sh install" >&2
    exit 2
  fi
}

case "$ACTION" in
  install)
    if [[ ! -x "$VENV_PYTHON" ]]; then
      run_checked python3 -m venv "${PROJECT_DIR}/venv"
    fi
    run_checked "$VENV_PYTHON" -m pip install --upgrade pip wheel "setuptools<81"
    run_checked "$VENV_PYTHON" -m pip install -r "${PROJECT_DIR}/requirements.txt"
    ;;
  env-template)
    mkdir -p "${PROJECT_DIR}/.runtime"
    if [[ ! -f "${PROJECT_DIR}/${ENV_FILE}" ]]; then
      cp "${PROJECT_DIR}/examples/kucoin.env.example" "${PROJECT_DIR}/${ENV_FILE}"
      echo "Created: ${PROJECT_DIR}/${ENV_FILE}"
    else
      echo "Already exists: ${PROJECT_DIR}/${ENV_FILE}"
    fi
    ;;
  train-fast)
    ensure_venv_python
    if [[ -z "$START" ]]; then START="2026-03-10T00:00:00Z"; fi
    if [[ -z "$END" ]]; then END="2026-03-11T00:00:00Z"; fi
    run_checked "$VENV_PYTHON" "$RUNNER" --mode train --episodes 10 --start "$START" --end "$END" --config "$CONFIG" --model-path "$MODEL_PATH" --env-file "$ENV_FILE"
    ;;
  train)
    ensure_venv_python
    ARGS=( "$VENV_PYTHON" "$RUNNER" --mode train --episodes "$EPISODES" --config "$CONFIG" --model-path "$MODEL_PATH" --env-file "$ENV_FILE" )
    if [[ -n "$START" ]]; then ARGS+=( --start "$START" ); fi
    if [[ -n "$END" ]]; then ARGS+=( --end "$END" ); fi
    run_checked "${ARGS[@]}"
    ;;
  shadow-once)
    ensure_venv_python
    run_checked "$VENV_PYTHON" "$RUNNER" --mode shadow --once --config "$CONFIG" --model-path "$MODEL_PATH" --env-file "$ENV_FILE"
    ;;
  shadow)
    ensure_venv_python
    run_checked "$VENV_PYTHON" "$RUNNER" --mode shadow --config "$CONFIG" --model-path "$MODEL_PATH" --env-file "$ENV_FILE"
    ;;
  live)
    ensure_venv_python
    run_checked "$VENV_PYTHON" "$RUNNER" --mode live --run-real-order --config "$CONFIG" --model-path "$MODEL_PATH" --env-file "$ENV_FILE"
    ;;
  test)
    ensure_venv_python
    PYTHONPATH="${PROJECT_DIR}/src" run_checked "$VENV_PYTHON" -m pytest "${PROJECT_DIR}/tests" -q
    ;;
  notebook)
    ensure_venv_python
    run_checked "$VENV_PYTHON" -m jupyter lab "${PROJECT_DIR}/notebooks/lecture16_basis_rl_colab.ipynb"
    ;;
  *)
    echo "Unknown action: $ACTION" >&2
    echo "Supported: install, env-template, train-fast, train, shadow-once, shadow, live, test, notebook" >&2
    exit 2
    ;;
esac

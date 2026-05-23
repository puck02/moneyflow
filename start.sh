#!/usr/bin/env bash
set -euo pipefail
cd /home/admin/workspace/moneyflow
export PYTHONPATH=/home/admin/workspace/moneyflow/backend
export MONEYFLOW_DB_PATH=/home/admin/workspace/moneyflow/data/moneyflow.db
exec /home/admin/.hermes/hermes-agent/venv/bin/python3 -m uvicorn studyflow.app:app --host 0.0.0.0 --port 5189

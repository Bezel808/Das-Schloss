#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip --version >/dev/null 2>&1 || .venv/bin/python -m ensurepip
.venv/bin/python -m pip install --require-hashes -r requirements.lock
exec .venv/bin/python -m uvicorn scholartrace.server:app --host 127.0.0.1 --port 8000

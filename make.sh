#!/usr/bin/env bash
# ./make.sh        check + run brick.py   (args go to the program, e.g. ./make.sh gui)
# ./make.sh build  check syntax + imports only (shared venv: $LB/py/venv)
# ./make.sh clean  remove __pycache__
set -e
cd "$(dirname "$0")"
. "$HOME/an/lb/env.sh"
MAIN=brick.py
SRC=*.py   # top level only: tests/ and old/ find their imports at run time

case "${1:-}" in
  build) exec "$LB_PY" "$LB/py/check.py" $SRC ;;
  clean) find . -name __pycache__ -type d -prune -exec rm -r {} +; exit ;;
esac
"$LB_PY" "$LB/py/check.py" $SRC
exec "$LB_PY" "$MAIN" "$@"

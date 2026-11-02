#!/usr/bin/env bash
# rerun on every .py save
cd "$(dirname "$0")"
exec "$HOME/an/lb/bin/watchexec" -r -e py -- ./make.sh "$@"

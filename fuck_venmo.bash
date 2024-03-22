#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")"

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
    exec poetry run ./fuck_venmo.bash "$@"
fi


if ! diff -q poetry.lock "${VIRTUAL_ENV}/poetry.lock" &>/dev/null; then
    poetry install
    cp poetry.lock "${VIRTUAL_ENV}/poetry.lock"
fi

python -m fuck_venmo "$@"

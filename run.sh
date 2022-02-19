#!/bin/sh
set -e
cd "${0%/*}"
cd src
python3 -m venv ../env
. ../env/bin/activate
python -m DarkChess "$@"

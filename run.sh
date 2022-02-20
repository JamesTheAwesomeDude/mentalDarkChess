#!/bin/sh
set -e
cd "${0%/*}"
python3 -m venv env
. env/bin/activate
pip install -r requirements.txt
cd src
python -m DarkChess "$@"

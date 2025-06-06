#!/usr/bin/env bash
cd /home/josh/smartcar || exit
set -a
source .env
set +a
# Activate venv and run script
. .venv/bin/activate
python smart.py

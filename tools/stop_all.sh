#!/usr/bin/env bash
set -euo pipefail
touch runtime/stop
sleep 1
rm -f runtime/stop

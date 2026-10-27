#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
.venv/bin/python -m legacy_lens.cli run \
  --repo testdata/rocketmq \
  --index artifacts/rocketmq.scip \
  --out-dir artifacts \
  --modules namesrv,broker,remoting

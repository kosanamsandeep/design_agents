#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export JAVA_HOME="${JAVA_HOME:-/home/sande/tools/jdk-21.0.12+8}"
export PATH="$HOME/.local/bin:$JAVA_HOME/bin:/home/sande/tools/apache-maven-3.9.16/bin:$PATH"
if [ ! -d "$ROOT/testdata/rocketmq" ]; then
  mkdir -p "$ROOT/testdata"
  git clone --depth 1 --branch rocketmq-all-5.5.1 \
    https://github.com/apache/rocketmq.git "$ROOT/testdata/rocketmq"
fi
cd "$ROOT/testdata/rocketmq"
mkdir -p "$ROOT/artifacts"
scip-java index --build-tool=maven --output "$ROOT/artifacts/rocketmq.scip"
echo "index: $ROOT/artifacts/rocketmq.scip"

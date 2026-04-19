#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${ROOT}/build"
mkdir -p "${OUT_DIR}"

CXX="${CXX:-g++}"
CXXFLAGS="${CXXFLAGS:--O2 -pipe -std=c++17}"

"${CXX}" ${CXXFLAGS} -pthread \
  -I"${ROOT}/src" \
  -o "${OUT_DIR}/pockettts_server" \
  "${ROOT}/src/main.cpp"

echo "Built ${OUT_DIR}/pockettts_server"

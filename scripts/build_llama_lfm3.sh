#!/usr/bin/env bash
# Build (or install) a llama.cpp runtime able to serve LFM3-Omni (text + vision
# + audio) for the Hanauta AI popup, then verify it actually loads.
#
# LFM3-Omni needs the llama.cpp build documented on the model card: commit
# d05706b4b plus the serving-guide server patch. This script pins both, builds
# only the `llama-server` target, and installs it where the popup looks for it.
#
# Usage:
#   ./scripts/build_llama_lfm3.sh                        # CPU build + verify if SMOKE_MODEL set
#   BACKENDS="cpu cuda" ./scripts/build_llama_lfm3.sh    # build matrix
#   ./scripts/build_llama_lfm3.sh --verify MODEL.gguf MMPROJ.gguf
#   PATCH_URL=https://.../lfm3.patch ./scripts/build_llama_lfm3.sh
#   PREBUILT_URL=https://.../llama-server-lfm3.tar.gz ./scripts/build_llama_lfm3.sh
#   ./scripts/build_llama_lfm3.sh --dry-run
#
# Environment:
#   LLAMA_REPO   git URL                  (default: ggml-org/llama.cpp)
#   LLAMA_REF    branch / tag / commit    (default: d05706b4b — the evaluated commit)
#   PATCH_URL    server patch to apply    (the card's "documented server patch")
#   PATCH_FILE   local patch file         (takes precedence over PATCH_URL)
#   BACKENDS     space separated matrix   (default: cpu; also cuda, vulkan, hip, metal)
#   PREFIX       install root             (default: ~/.cache/hanauta-ai-popup/runtimes/lfm3-llama-cpp)
#   JOBS         parallel build jobs      (default: nproc - 1)
#   CMAKE_EXTRA  extra -D flags           (appended to the backend flags)
#   SMOKE_MODEL  GGUF to load after build (enables verification)
#   SMOKE_MMPROJ mmproj to load with it
#   VERIFY_TIMEOUT  seconds to wait for the server (default: 180)
set -euo pipefail

LLAMA_REPO="${LLAMA_REPO:-https://github.com/ggml-org/llama.cpp.git}"
LLAMA_REF="${LLAMA_REF:-d05706b4b}"
PATCH_URL="${PATCH_URL:-}"
PATCH_FILE="${PATCH_FILE:-}"
BACKENDS="${BACKENDS:-${COMPUTE_BACKEND:-cpu}}"
BASE_PREFIX="${PREFIX:-$HOME/.cache/hanauta-ai-popup/runtimes/lfm3-llama-cpp}"
JOBS="${JOBS:-$(( $(nproc 2>/dev/null || echo 2) > 1 ? $(nproc) - 1 : 1 ))}"
CMAKE_EXTRA="${CMAKE_EXTRA:-}"
PREBUILT_URL="${PREBUILT_URL:-}"
SMOKE_MODEL="${SMOKE_MODEL:-}"
SMOKE_MMPROJ="${SMOKE_MMPROJ:-}"
VERIFY_TIMEOUT="${VERIFY_TIMEOUT:-180}"
TARGET="${TARGET:-llama-server}"
DRY_RUN="${DRY_RUN:-0}"
FORCE="${FORCE:-0}"
VERIFY_MODEL=""
VERIFY_MMPROJ=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --force) FORCE=1; shift ;;
    --verify)
      # Consume: --verify MODEL [MMPROJ]
      VERIFY_MODEL="${2:-}"
      VERIFY_MMPROJ="${3:-}"
      if [ $# -ge 3 ]; then
        shift 3
      elif [ $# -ge 2 ]; then
        shift 2
      else
        shift
      fi
      ;;
    -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

say() { printf '[lfm3-build] %s\n' "$*"; }
die() { printf '[lfm3-build] ERROR: %s\n' "$*" >&2; exit 1; }

free_port() {
  python3 - <<'PY' 2>/dev/null || echo $(( 8200 + RANDOM % 400 ))
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
}

backend_flags() {
  case "$1" in
    cpu)   echo "" ;;
    cuda)  echo "-DGGML_CUDA=ON" ;;
    vulkan) echo "-DGGML_VULKAN=ON" ;;
    hip|rocm) echo "-DGGML_HIP=ON" ;;
    metal) echo "-DGGML_METAL=ON" ;;
    *) die "unknown backend: $1" ;;
  esac
}

# Boot the server against a real model and wait until it is serving.
verify_runtime() {
  local binary="$1" model="$2" mmproj="${3:-}"
  [ -n "$model" ] || { say "verify: no model given, skipping"; return 0; }
  [ -x "$binary" ] || die "verify: not executable: $binary"
  [ -f "$model" ] || die "verify: model not found: $model"
  local port logf pid ok
  port="$(free_port)"
  logf="$(mktemp)"
  local args=("$binary" -m "$model" --jinja --reasoning off -c 512 --host 127.0.0.1 --port "$port")
  if [ -n "$mmproj" ]; then
    [ -f "$mmproj" ] || die "verify: mmproj not found: $mmproj"
    args+=(--mmproj "$mmproj")
  fi
  say "verify: starting $(basename "$binary") on 127.0.0.1:$port (mmproj: ${mmproj:-none})"
  "${args[@]}" >"$logf" 2>&1 &
  pid=$!
  ok=0
  local waited=0
  while [ "$waited" -lt "$VERIFY_TIMEOUT" ]; do
    if ! kill -0 "$pid" 2>/dev/null; then break; fi
    if grep -qiE "server is listening|all slots are idle|model loaded" "$logf" 2>/dev/null; then ok=1; break; fi
    if command -v curl >/dev/null 2>&1 && curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; then ok=1; break; fi
    sleep 1
    waited=$(( waited + 1 ))
  done
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  if [ "$ok" -ne 1 ]; then
    say "verify: FAILED after ${waited}s"
    tail -n 25 "$logf" >&2 || true
    rm -f "$logf"
    return 1
  fi
  say "verify: OK (model${mmproj:+ + mmproj} loaded, ${waited}s)"
  rm -f "$logf"
  return 0
}

# Fast path: install a prebuilt archive so users need no toolchain at all.
install_prebuilt() {
  local prefix="$1"
  for tool in curl tar; do command -v "$tool" >/dev/null 2>&1 || die "missing required tool: $tool"; done
  local work archive found
  work="$(mktemp -d)"
  archive="$work/llama-server-prebuilt"
  say "downloading prebuilt runtime: $PREBUILT_URL"
  curl -fL --retry 3 --connect-timeout 20 -o "$archive" "$PREBUILT_URL"
  case "$PREBUILT_URL" in
    *.zip) command -v unzip >/dev/null 2>&1 || die "unzip is required for .zip archives"; unzip -q "$archive" -d "$work/x" ;;
    *) mkdir -p "$work/x"; tar -xf "$archive" -C "$work/x" ;;
  esac
  found="$(find "$work/x" -type f -name 'llama-server' -perm -u+x | head -n 1)"
  [ -n "$found" ] || found="$(find "$work/x" -type f -name 'llama-server' | head -n 1)"
  [ -n "$found" ] || die "archive did not contain a llama-server binary"
  mkdir -p "$prefix"
  cp -a "$(dirname "$found")/." "$prefix/"
  chmod +x "$prefix/llama-server"
  rm -rf "$work"
  say "installed prebuilt runtime: $prefix/llama-server"
}

build_one() {
  local backend="$1" prefix="$2"
  local src_dir="$prefix/src" build_dir="$prefix/src/build" bin_path="$prefix/llama-server"
  local extra
  extra="$(backend_flags "$backend")"
  [ -n "$CMAKE_EXTRA" ] && extra="$extra $CMAKE_EXTRA"

  say "== backend: $backend =="
  say "   prefix: $prefix"
  if [ -x "$bin_path" ] && [ "$FORCE" -eq 0 ]; then
    say "   already installed: $bin_path (use --force to rebuild)"
    return 0
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    say "   cmake flags: ${extra:-<none>}"
    return 0
  fi

  mkdir -p "$prefix"
  for tool in git cmake; do
    command -v "$tool" >/dev/null 2>&1 || die "missing required tool: $tool (install git + cmake + a C/C++ toolchain)"
  done
  if ! command -v cc >/dev/null 2>&1 && ! command -v gcc >/dev/null 2>&1 && ! command -v clang >/dev/null 2>&1; then
    die "no C/C++ compiler found (install build-essential / base-devel / gcc)"
  fi

  if [ ! -d "$src_dir/.git" ]; then
    say "   cloning $LLAMA_REPO"
    git clone --depth 1 --branch "$LLAMA_REF" "$LLAMA_REPO" "$src_dir" 2>/dev/null \
      || git clone "$LLAMA_REPO" "$src_dir"
  else
    say "   reusing existing source tree"
    git -C "$src_dir" fetch --all --tags --quiet || true
  fi

  say "   checking out $LLAMA_REF"
  git -C "$src_dir" checkout "$LLAMA_REF" 2>/dev/null || git -C "$src_dir" checkout -B "$LLAMA_REF" "origin/$LLAMA_REF"

  # The card's build is the pinned commit *plus* the serving-guide server patch.
  if [ -n "$PATCH_FILE" ]; then
    [ -f "$PATCH_FILE" ] || die "PATCH_FILE not found: $PATCH_FILE"
    say "   applying patch: $PATCH_FILE"
    git -C "$src_dir" apply --whitespace=nowarn "$PATCH_FILE"
  elif [ -n "$PATCH_URL" ]; then
    command -v curl >/dev/null 2>&1 || die "curl is required to fetch PATCH_URL"
    local patch_tmp
    patch_tmp="$(mktemp)"
    say "   downloading patch: $PATCH_URL"
    curl -fL --retry 3 --connect-timeout 20 -o "$patch_tmp" "$PATCH_URL"
    git -C "$src_dir" apply --whitespace=nowarn "$patch_tmp"
    rm -f "$patch_tmp"
  fi

  say "   configuring (${extra:-no backend flags})"
  # shellcheck disable=SC2086
  cmake -S "$src_dir" -B "$build_dir" -DCMAKE_BUILD_TYPE=Release $extra

  say "   building $TARGET (jobs=$JOBS)"
  cmake --build "$build_dir" --config Release -j "$JOBS" --target "$TARGET" \
    || cmake --build "$build_dir" --config Release -j "$JOBS" --target server

  local found=""
  for candidate in "$build_dir/bin/llama-server" "$build_dir/bin/server" "$src_dir/llama-server" "$src_dir/server"; do
    if [ -f "$candidate" ] && [ -s "$candidate" ]; then found="$candidate"; break; fi
  done
  [ -n "$found" ] || die "build finished but no llama-server binary was produced"
  cp -a "$found" "$bin_path"
  chmod +x "$bin_path"
  find "$(dirname "$found")" -maxdepth 1 -name 'lib*.so*' -exec cp -a {} "$prefix/" \; 2>/dev/null || true
  say "   installed: $bin_path"
}

say "repo:     $LLAMA_REPO"
say "ref:      $LLAMA_REF"
say "backends: $BACKENDS"
say "prefix:   $BASE_PREFIX"
say "jobs:     $JOBS"
[ -n "$PATCH_FILE" ] && say "patch:    $PATCH_FILE"
[ -n "$PATCH_URL" ] && say "patch:    $PATCH_URL"
[ -n "$PREBUILT_URL" ] && say "prebuilt: $PREBUILT_URL"
[ -n "$SMOKE_MODEL" ] && say "smoke:    $SMOKE_MODEL"

# --verify is a pure verification pass: never build as a side effect.
if [ -n "$VERIFY_MODEL" ]; then
  binary="$BASE_PREFIX/llama-server"
  [ -x "$binary" ] || binary="$BASE_PREFIX/current/llama-server"
  for backend in $BACKENDS; do
    [ -x "$binary" ] && break
    [ -x "$BASE_PREFIX/$backend/llama-server" ] && binary="$BASE_PREFIX/$backend/llama-server" && break
  done
  [ -x "$binary" ] || die "no installed llama-server under $BASE_PREFIX — build first, or pass PREBUILT_URL"
  verify_runtime "$binary" "$VERIFY_MODEL" "$VERIFY_MMPROJ"
  say "done"
  exit 0
fi

status=0
for backend in $BACKENDS; do
  if [ -n "$PREBUILT_URL" ]; then
    install_prebuilt "$BASE_PREFIX/$backend"
  else
    build_one "$backend" "$BASE_PREFIX/$backend" || status=$?
  fi
  [ "$status" -eq 0 ] || continue
  if [ "$DRY_RUN" -eq 0 ]; then
    model="${VERIFY_MODEL:-$SMOKE_MODEL}"
    mmproj="${VERIFY_MMPROJ:-$SMOKE_MMPROJ}"
    if [ -n "$model" ]; then
      verify_runtime "$BASE_PREFIX/$backend/llama-server" "$model" "$mmproj" || status=$?
    fi
    # Convenience: keep the last built backend as the popup's default location.
    ln -sfn "$BASE_PREFIX/$backend" "$BASE_PREFIX/current" 2>/dev/null || true
  fi
done

if [ "$status" -ne 0 ]; then
  die "one or more backends failed"
fi
say "done"

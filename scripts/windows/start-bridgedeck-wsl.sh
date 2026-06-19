#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bridge_root="${BRIDGEDECK_ROOT:-$(cd "${script_dir}/../.." && pwd)}"

cd "${bridge_root}"

if [[ -n "${BRIDGEDECK_WINDOWS_HOME:-}" ]]; then
  export HOME="${BRIDGEDECK_WINDOWS_HOME}"
fi

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

if [[ "${BRIDGEDECK_SKIP_PROXY:-0}" != "1" ]]; then
  proxy_host="${BRIDGEDECK_WINDOWS_PROXY_HOST:-}"
  if [[ -z "${proxy_host}" ]]; then
    proxy_host="$(ip route show default | awk '{print $3; exit}')"
  fi

  if [[ -n "${proxy_host}" ]]; then
    proxy_port="${BRIDGEDECK_WINDOWS_PROXY_RELAY_PORT:-17897}"
    proxy_url="http://${proxy_host}:${proxy_port}"
    export HTTP_PROXY="${proxy_url}"
    export HTTPS_PROXY="${proxy_url}"
    export ALL_PROXY="${proxy_url}"
    export http_proxy="${proxy_url}"
    export https_proxy="${proxy_url}"
    export all_proxy="${proxy_url}"
    export CODEX_BRIDGE_UPSTREAM_PROXY="${proxy_url}"
    export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost,::1}"
    export no_proxy="${NO_PROXY}"
  fi
fi

exec python3 bridgedeck.py --host "${BRIDGEDECK_HOST:-127.0.0.1}" --port "${BRIDGEDECK_PORT:-8899}"

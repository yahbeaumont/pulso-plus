#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
export PORT="${PORT:-3000}"
export PULSO_INTERNAL_PORT="${PULSO_INTERNAL_PORT:-8502}"
export PULSO_PUBLIC_DEPLOY=1
if [[ ! "$PORT" =~ ^[0-9]+$ || ! "$PULSO_INTERNAL_PORT" =~ ^[0-9]+$ || "$PORT" == "$PULSO_INTERNAL_PORT" ]]; then
  echo 'Configuração de porta inválida.' >&2
  exit 1
fi
python deploy/verify_artifact.py
export PULSO_APP_ROOT="$PWD"
envsubst '${PORT} ${PULSO_INTERNAL_PORT} ${PULSO_APP_ROOT}' < deploy/nginx.conf.template > /tmp/pulso-nginx.conf
python -m streamlit run app.py --server.address 127.0.0.1 --server.port "$PULSO_INTERNAL_PORT" --server.headless true --server.fileWatcherType none --browser.gatherUsageStats false &
app_pid=$!
nginx -c /tmp/pulso-nginx.conf -p /tmp -g 'daemon off;' &
proxy_pid=$!
cleanup() {
  kill -TERM "$app_pid" "$proxy_pid" 2>/dev/null || true
  wait "$app_pid" "$proxy_pid" 2>/dev/null || true
  rm -f /tmp/pulso-nginx.conf
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
set +e
wait -n "$app_pid" "$proxy_pid"
status=$?
set -e
if [ "$status" -eq 0 ]; then status=1; fi
exit "$status"

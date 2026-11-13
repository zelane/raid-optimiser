#!/bin/sh
# Start mitmproxy on 127.0.0.1:8080, intercepting TLS only for hellhades.com
# (everything else is tunnelled through untouched). Uses uvx so mitmproxy
# needn't be installed system-wide.
cd "$(dirname "$0")" || exit 1
[ -x bin/raid-decoder ] || dotnet build decoder -c Release -o bin || exit 1
exec uvx --from mitmproxy mitmdump \
  --listen-host 127.0.0.1 --listen-port 8080 \
  --allow-hosts 'hellhades\.com(:\d+)?$' \
  -s capture/hh_capture.py \
  --flow-detail 1 "$@"

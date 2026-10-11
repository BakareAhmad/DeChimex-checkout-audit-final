#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Final clean run for the mobile gallery fix (2026-10-06).
# Rebuild -> full automated suite -> fresh app instance -> ONE browser journey.
# evidence/ at the EmailDesign root is written by this script only; a
# non-empty evidence/ aborts so runs never mix.
# ---------------------------------------------------------------------------
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"                     # EmailDesign/
SOLUTION="$ROOT/DeChimexPrints"
EVID="$ROOT/evidence"
PORT="${PORT:-5119}"

export PATH=/var/tmp/dotnet:$PATH DOTNET_ROOT=/var/tmp/dotnet NUGET_PACKAGES=/var/tmp/nuget
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
export PLAYWRIGHT_BROWSERS_PATH=/var/tmp/ms-playwright
export GALLERY_EVID="$EVID"

if [ -d "$EVID" ] && [ -n "$(ls -A "$EVID" 2>/dev/null)" ]; then
  echo "ABORT: $EVID is not empty - archive the previous final run first." >&2
  exit 1
fi
mkdir -p "$EVID" "$HERE/media"

echo "== [1/6] build =="
( cd "$SOLUTION" && dotnet build -c Debug --nologo -v q ) > "$EVID/log-1-build.txt" 2>&1
tail -1 "$EVID/log-1-build.txt"

echo "== [2/6] automated test suite (-m:1) =="
( cd "$SOLUTION" && dotnet test -m:1 --no-build ) > "$EVID/log-2-tests.txt" 2>&1
grep -E "Passed!|Failed!" "$EVID/log-2-tests.txt" | tail -4

echo "== [3/6] test media =="
cp "$SOLUTION/src/DeChimex.Host/wwwroot/img/logo.png"    "$HERE/media/shot-a.png"
cp "$SOLUTION/src/DeChimex.Host/wwwroot/img/icon-192.png" "$HERE/media/shot-b.png"
ffmpeg -y -v error -f lavfi -i testsrc2=size=640x360:rate=25:duration=2 \
  -c:v libx264 -pix_fmt yuv420p -movflags +faststart "$HERE/media/clip.mp4"
head -c 11534336 /dev/urandom > "$HERE/media/huge.mp4"    # 11 MB > the 10 MB cap
printf 'MZ-junk-not-a-program' > "$HERE/media/bad.exe"
ls -la "$HERE/media" | tee "$EVID/log-3-media.txt"

echo "== [4/6] fresh app instance (InMemory, :$PORT) =="
pkill -f "dotnet run --project src/DeChimex.Host" 2>/dev/null || true
pkill -f "DeChimex.Host.dll" 2>/dev/null || true
sleep 2
( cd "$SOLUTION" && ASPNETCORE_ENVIRONMENT=Development \
  ASPNETCORE_URLS="http://0.0.0.0:$PORT" \
  Database__UseInMemory=true \
  Brevo__ApiBaseUrl=http://127.0.0.1:9999 \
  Paystack__ApiBaseUrl=http://127.0.0.1:9090 \
  dotnet run --project src/DeChimex.Host --no-build --no-launch-profile -c Debug ) \
  > "$EVID/log-4-app.txt" 2>&1 &
APP_PID=$!
cleanup() { kill "$APP_PID" 2>/dev/null || true; pkill -f "DeChimex.Host.dll" 2>/dev/null || true; }
trap cleanup EXIT
for _ in $(seq 1 90); do
  curl -sf "http://127.0.0.1:$PORT/" > /dev/null 2>&1 && break
  sleep 2
done
curl -sf "http://127.0.0.1:$PORT/" > /dev/null || { echo "ABORT: app did not start" >&2; exit 1; }
echo "app up on :$PORT"

echo "== [5/6] browser journey (single evidence source) =="
python3 "$HERE/gallery_e2e.py" 2>&1 | tee "$EVID/log-5-journey.txt"

echo "== [6/6] app log tail =="
tail -20 "$EVID/log-4-app.txt" > "$EVID/log-6-app-tail.txt" || true
echo "FINAL RUN COMPLETE -> $EVID"

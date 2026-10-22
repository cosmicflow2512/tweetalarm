#!/bin/sh
# Startet RSSHub und tweetalarm. Beendet sich einer, stoppt der Container,
# damit Docker/Unraid ihn per Restart-Policy neu startet.
set -u

cd /app
npm run start &
RSSHUB_PID=$!

HEALTH_URL="http://127.0.0.1:${PORT:-1200}/healthz"
[ -n "${ACCESS_KEY:-}" ] && HEALTH_URL="${HEALTH_URL}?key=${ACCESS_KEY}"

echo "[start] warte auf RSSHub ..."
i=0
until curl -fs "$HEALTH_URL" >/dev/null 2>&1; do
  if ! kill -0 "$RSSHUB_PID" 2>/dev/null; then
    echo "[start] RSSHub ist beim Start abgestuerzt"
    exit 1
  fi
  i=$((i + 1))
  if [ "$i" -ge 120 ]; then
    echo "[start] RSSHub nach 120 s nicht erreichbar"
    kill "$RSSHUB_PID" 2>/dev/null
    exit 1
  fi
  sleep 1
done
echo "[start] RSSHub laeuft, starte tweetalarm"

/opt/tweetalarm/venv/bin/python /opt/tweetalarm/app.py &
ALARM_PID=$!

trap 'kill -TERM "$RSSHUB_PID" "$ALARM_PID" 2>/dev/null' TERM INT

# Warten bis einer der beiden endet
while kill -0 "$RSSHUB_PID" 2>/dev/null && kill -0 "$ALARM_PID" 2>/dev/null; do
  sleep 2
done

echo "[start] ein Prozess wurde beendet, stoppe Container"
kill -TERM "$RSSHUB_PID" "$ALARM_PID" 2>/dev/null
wait
exit 1

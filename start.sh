#!/bin/sh
# Startet RSSHub und tweetalarm. tweetalarm kann per Flag-Datei einen
# Neustart nur des RSSHub-Prozesses anfordern (Selbstheilung).
# Stirbt ein Prozess unerwartet, beendet sich der Container (Restart-Policy).
set -u

FLAG="${RESTART_FLAG:-/tmp/tweetalarm-restart-rsshub}"
HEALTH_URL="http://127.0.0.1:${PORT:-1200}/healthz"
[ -n "${ACCESS_KEY:-}" ] && HEALTH_URL="${HEALTH_URL}?key=${ACCESS_KEY}"
RSSHUB_PID=""
ALARM_PID=""

start_rsshub() {
  cd /app
  # eigene Prozessgruppe, damit npm -> cross-env -> node gemeinsam beendet werden kann
  setsid npm run start &
  RSSHUB_PID=$!
  echo "[start] warte auf RSSHub ..."
  i=0
  until curl -fs "$HEALTH_URL" >/dev/null 2>&1; do
    if ! kill -0 "$RSSHUB_PID" 2>/dev/null; then
      echo "[start] RSSHub ist beim Start abgestuerzt"
      return 1
    fi
    i=$((i + 1))
    if [ "$i" -ge 120 ]; then
      echo "[start] RSSHub nach 120 s nicht erreichbar"
      return 1
    fi
    sleep 1
  done
  echo "[start] RSSHub laeuft"
}

stop_rsshub() {
  [ -n "$RSSHUB_PID" ] || return 0
  kill -TERM "-$RSSHUB_PID" 2>/dev/null
  j=0
  while kill -0 "-$RSSHUB_PID" 2>/dev/null && [ "$j" -lt 15 ]; do sleep 1; j=$((j + 1)); done
  kill -KILL "-$RSSHUB_PID" 2>/dev/null
  wait "$RSSHUB_PID" 2>/dev/null
}

stop_all() {
  [ -n "$ALARM_PID" ] && kill -TERM "$ALARM_PID" 2>/dev/null
  stop_rsshub
  wait
}

trap 'stop_all; exit 0' TERM INT

rm -f "$FLAG"
start_rsshub || { stop_all; exit 1; }

echo "[start] starte tweetalarm"
/opt/tweetalarm/venv/bin/python /opt/tweetalarm/app.py &
ALARM_PID=$!

while :; do
  if [ -f "$FLAG" ]; then
    rm -f "$FLAG"
    echo "[start] Selbstheilung: starte RSSHub neu"
    stop_rsshub
    start_rsshub || { stop_all; exit 1; }
  fi
  if ! kill -0 "$ALARM_PID" 2>/dev/null || ! kill -0 "$RSSHUB_PID" 2>/dev/null; then
    echo "[start] ein Prozess wurde beendet, stoppe Container"
    stop_all
    exit 1
  fi
  sleep 2
done

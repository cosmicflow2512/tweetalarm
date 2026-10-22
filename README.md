# tweetalarm

Überwacht X/Twitter-Accounts und löst bei jedem neuen Tweet einen Pushover-Alarm aus. [RSSHub](https://docs.rsshub.app/) ist im Container enthalten (Basis: `diygod/rsshub:latest`), es wird nur ein Container benötigt. Das Image wird wöchentlich neu gebaut, damit RSSHub-Updates ankommen.

- **emergency** (Standard): Pushover Priority 2. Wird alle `EMERGENCY_RETRY` Sekunden wiederholt, bis der Alarm in der App bestätigt wird oder `EMERGENCY_EXPIRE` abläuft. Pushover-Grenzen: retry ≥ 30 s, expire ≤ 10800 s, max. 50 Wiederholungen ([API-Doku](https://pushover.net/api#priority)).
- **burst**: `BURST_COUNT` Einzelnachrichten im Abstand von `BURST_DELAY` Sekunden, sequenziell.

Fällt der Feed `FAIL_ALERT_THRESHOLD`-mal in Folge aus (z. B. abgelaufener auth_token), kommt eine Störungsmeldung, damit ein stiller Ausfall nicht unbemerkt bleibt.

Beim ersten Lauf werden vorhandene Tweets nur als gesehen markiert, es gibt keinen Alarm.

## Setup

1. Zweitaccount bei X anlegen, auf x.com einloggen, Cookie `auth_token` auslesen (DevTools → Application → Cookies).
2. Pushover-App registrieren: <https://pushover.net/apps/build> → App-Token. User-Key steht im Dashboard.
3. Container starten (`unraid/tweetalarm.xml`) mit `TWITTER_AUTH_TOKEN`, `ACCOUNTS`, `PUSHOVER_TOKEN`, `PUSHOVER_USER`.
4. Test: `http://UNRAID-IP:1200/twitter/user/<name>` muss einen Feed liefern. Der Port wird nur dafür gebraucht.
5. iPhone: Pushover-App → Einstellungen → „Critical Alerts for high-priority“ aktivieren, damit Stummschalter und Fokus umgangen werden ([Pushover-Blog](https://blog.pushover.net/posts/2020/2/ios-critical-alerts)).

## Variablen

| Variable | Default | Beschreibung |
|---|---|---|
| `ACCOUNTS` | – | Benutzernamen ohne @, kommagetrennt |
| `TWITTER_AUTH_TOKEN` | – | RSSHub: auth_token-Cookie |
| `CACHE_EXPIRE` | `60` | RSSHub-Route-Cache in Sekunden |
| `ACCESS_KEY` | – | Optional, schützt RSSHub; tweetalarm nutzt ihn automatisch |
| `RSSHUB_URL` | `http://127.0.0.1:1200` | Nur ändern, wenn ein externes RSSHub genutzt werden soll |
| `PUSHOVER_TOKEN` / `PUSHOVER_USER` | – | Pflicht |
| `PUSHOVER_DEVICE` / `PUSHOVER_SOUND` | – | Optional |
| `MODE` | `emergency` | `emergency` oder `burst` |
| `EMERGENCY_RETRY` / `EMERGENCY_EXPIRE` | `30` / `3600` | Sekunden |
| `BURST_COUNT` / `BURST_DELAY` / `BURST_PRIORITY` | `10` / `2` / `1` | Nur burst |
| `POLL_INTERVAL` | `60` | Sekunden |
| `INCLUDE_RETWEETS` / `INCLUDE_REPLIES` | `false` | RSSHub-Parameter `includeRts` / `includeReplies` |
| `FAIL_ALERT_THRESHOLD` / `FAIL_ALERT_REPEAT_MIN` | `5` / `60` | Störungsmeldung |
| `TEST_ON_START` | `false` | Testalarm beim Start |
| `STATE_DIR` | `/data` | State-Datei |

## Hinweise

- RSSHub cached Routen standardmäßig 300 s (`CACHE_EXPIRE`). Für schnelle Alarme in RSSHub `CACHE_EXPIRE=60` setzen. Gesamtlatenz ≈ `CACHE_EXPIRE` + `POLL_INTERVAL`.
- Die Twitter-Route nutzt die Web-API mit einem echten Account. Das verstößt gegen die X-ToS; der Account kann gesperrt werden. Zu häufiges Polling erhöht das Risiko.

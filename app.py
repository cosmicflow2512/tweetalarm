#!/usr/bin/env python3
"""tweetalarm - pollt RSSHub-Twitter-Feeds und alarmiert per Pushover."""
import html
import json
import logging
import os
import re
import signal
import sys
import time
from pathlib import Path
from urllib.parse import quote

import feedparser
import requests

PUSHOVER_API = "https://api.pushover.net/1/messages.json"


def env(name, default=None, cast=str):
    v = os.environ.get(name, "").strip()
    return default if v == "" else cast(v)


def env_bool(name, default=False):
    v = os.environ.get(name, "").strip().lower()
    return default if v == "" else v in ("1", "true", "yes", "on")


RSSHUB_URL = env("RSSHUB_URL", "http://127.0.0.1:1200").rstrip("/")
# Im Kombi-Container teilen sich RSSHub und tweetalarm ACCESS_KEY
RSSHUB_ACCESS_KEY = env("RSSHUB_ACCESS_KEY", "") or env("ACCESS_KEY", "")
ACCOUNTS = [a.strip().lstrip("@") for a in env("ACCOUNTS", "").split(",") if a.strip()]
INCLUDE_RTS = env_bool("INCLUDE_RETWEETS", False)
INCLUDE_REPLIES = env_bool("INCLUDE_REPLIES", False)
POLL_INTERVAL = env("POLL_INTERVAL", 60, int)
REQUEST_TIMEOUT = env("TWEETALARM_TIMEOUT", 30, int)  # REQUEST_TIMEOUT gehoert RSSHub (ms)

PO_TOKEN = env("PUSHOVER_TOKEN", "")
PO_USER = env("PUSHOVER_USER", "")
PO_DEVICE = env("PUSHOVER_DEVICE", "")
PO_SOUND = env("PUSHOVER_SOUND", "")

# MODE: emergency = priority 2, wiederholt bis Bestaetigung
#       burst     = BURST_COUNT Einzelnachrichten
MODE = env("MODE", "emergency").lower()
RETRY = max(30, env("EMERGENCY_RETRY", 30, int))
EXPIRE = min(10800, env("EMERGENCY_EXPIRE", 3600, int))
BURST_COUNT = env("BURST_COUNT", 10, int)
BURST_DELAY = env("BURST_DELAY", 2.0, float)
BURST_PRIORITY = env("BURST_PRIORITY", 1, int)

# Simulierter Tweet X Sekunden nach Start (0 = aus)
TEST_TWEET_DELAY = env("TEST_TWEET_DELAY", 0, int)

FAIL_THRESHOLD = env("FAIL_ALERT_THRESHOLD", 5, int)
FAIL_REPEAT = env("FAIL_ALERT_REPEAT_MIN", 60, int) * 60
STATE_FILE = Path(env("STATE_DIR", "/data")) / "state.json"
KEEP_IDS = 300

logging.basicConfig(
    level=env("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("tweetalarm")
session = requests.Session()
running = True


def stop(*_):
    global running
    running = False


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except FileNotFoundError:
        return {}
    except Exception as e:
        log.error("State-Datei unlesbar (%s), starte leer", e)
        return {}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(STATE_FILE)


def feed_url(account):
    params = [f"includeRts={'true' if INCLUDE_RTS else 'false'}",
              f"includeReplies={'true' if INCLUDE_REPLIES else 'false'}"]
    url = f"{RSSHUB_URL}/twitter/user/{quote(account)}/{'&'.join(params)}"
    if RSSHUB_ACCESS_KEY:
        url += f"?key={quote(RSSHUB_ACCESS_KEY)}"
    return url


def fetch(account):
    r = session.get(feed_url(account), timeout=REQUEST_TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]!r}")
    feed = feedparser.parse(r.content)
    if feed.bozo and not feed.entries:
        raise RuntimeError(f"Feed nicht parsebar: {feed.bozo_exception}")
    return feed.entries


def clean(text):
    text = re.sub(r"<br\s*/?>", "\n", text or "", flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def pushover(title, message, url=None, priority=0, extra=None):
    data = {
        "token": PO_TOKEN,
        "user": PO_USER,
        "title": title[:250],
        "message": (message or "-")[:1024],
        "priority": priority,
    }
    if PO_DEVICE:
        data["device"] = PO_DEVICE
    if PO_SOUND:
        data["sound"] = PO_SOUND
    if url:
        data["url"] = url[:512]
        data["url_title"] = "Tweet oeffnen"
    if extra:
        data.update(extra)
    for attempt in range(1, 6):
        try:
            r = session.post(PUSHOVER_API, data=data, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            log.warning("Pushover nicht erreichbar (%s), Versuch %d", e, attempt)
            time.sleep(5 * attempt)
            continue
        if r.status_code == 200 and r.json().get("status") == 1:
            return True
        if 400 <= r.status_code < 500:
            # Laut Pushover-Doku: 4xx nicht wiederholen
            log.error("Pushover lehnt ab: %s %s", r.status_code, r.text[:300])
            return False
        log.warning("Pushover HTTP %s, Versuch %d", r.status_code, attempt)
        time.sleep(5 * attempt)
    return False


def alert_tweet(account, entry, test=False):
    title = f"{'[TEST] ' if test else ''}@{account} hat getwittert"
    body = clean(entry.get("description") or entry.get("summary") or entry.get("title"))
    link = entry.get("link")
    if MODE == "burst":
        for i in range(BURST_COUNT):
            pushover(f"{title} ({i + 1}/{BURST_COUNT})", body, link, BURST_PRIORITY)
            if i < BURST_COUNT - 1:
                time.sleep(BURST_DELAY)
    else:
        pushover(title, body, link, 2,
                 {"retry": RETRY, "expire": EXPIRE, "tags": f"tweetalarm,{account}"})


def simulate_tweet():
    account = ACCOUNTS[0]
    log.info("Simulierter Tweet fuer @%s (TEST_TWEET_DELAY=%ss)", account, TEST_TWEET_DELAY)
    alert_tweet(account, {
        "description": "Simulierter Tweet von tweetalarm. Wenn du das liest, funktioniert die Alarmkette.",
        "link": f"https://x.com/{account}",
    }, test=True)


def entry_id(e):
    return e.get("id") or e.get("guid") or e.get("link")


def check(account, state):
    acc = state.setdefault(account, {"seen": [], "fails": 0, "last_fail_alert": 0})
    try:
        entries = fetch(account)
    except Exception as e:
        acc["fails"] += 1
        log.warning("@%s: Abruf fehlgeschlagen (%d in Folge): %s", account, acc["fails"], e)
        now = time.time()
        if acc["fails"] >= FAIL_THRESHOLD and now - acc["last_fail_alert"] > FAIL_REPEAT:
            pushover("tweetalarm: Feed gestoert",
                     f"@{account}: {acc['fails']} Fehlversuche in Folge.\n{e}", priority=1)
            acc["last_fail_alert"] = now
        return
    if acc["fails"] >= FAIL_THRESHOLD:
        pushover("tweetalarm: Feed wieder ok", f"@{account} wird wieder gelesen.", priority=0)
    acc["fails"] = 0

    seen = set(acc["seen"])
    ids = [entry_id(e) for e in entries if entry_id(e)]
    if not acc["seen"]:
        acc["seen"] = ids[:KEEP_IDS]
        log.info("@%s: Erstlauf, %d bestehende Tweets als gesehen markiert", account, len(ids))
        return
    new = [e for e in entries if entry_id(e) and entry_id(e) not in seen]
    for e in reversed(new):  # aelteste zuerst
        log.info("@%s: neuer Tweet %s", account, e.get("link"))
        alert_tweet(account, e)
    if new:
        acc["seen"] = ([entry_id(e) for e in new] + acc["seen"])[:KEEP_IDS]


def main():
    missing = [n for n, v in (("ACCOUNTS", ACCOUNTS), ("PUSHOVER_TOKEN", PO_TOKEN),
                              ("PUSHOVER_USER", PO_USER)) if not v]
    if missing:
        log.error("Fehlende Variablen: %s", ", ".join(missing))
        sys.exit(1)
    log.info("Ueberwache %s via %s, Intervall %ss, Modus %s",
             ", ".join("@" + a for a in ACCOUNTS), RSSHUB_URL, POLL_INTERVAL, MODE)
    if env_bool("TEST_ON_START"):
        pushover("tweetalarm Test", "Testalarm beim Start.", priority=2 if MODE != "burst" else 1,
                 extra={"retry": RETRY, "expire": 120} if MODE != "burst" else None)
    state = load_state()
    test_due = time.monotonic() + TEST_TWEET_DELAY if TEST_TWEET_DELAY > 0 else None
    while running:
        for account in ACCOUNTS:
            if not running:
                break
            check(account, state)
        save_state(state)
        for _ in range(POLL_INTERVAL):
            if not running:
                break
            if test_due is not None and time.monotonic() >= test_due:
                test_due = None
                simulate_tweet()
            time.sleep(1)
    log.info("Beendet")


if __name__ == "__main__":
    main()

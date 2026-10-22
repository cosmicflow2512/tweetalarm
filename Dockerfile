# RSSHub + tweetalarm in einem Container.
# Basis: offizielles RSSHub-Image (node:24-trixie-slim, WORKDIR /app, ENTRYPOINT dumb-init)
FROM diygod/rsshub:latest

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /opt/tweetalarm/requirements.txt
RUN python3 -m venv /opt/tweetalarm/venv \
 && /opt/tweetalarm/venv/bin/pip install --no-cache-dir -r /opt/tweetalarm/requirements.txt

COPY app.py start.sh /opt/tweetalarm/
RUN chmod +x /opt/tweetalarm/start.sh

ENV PYTHONUNBUFFERED=1 \
    STATE_DIR=/data \
    RSSHUB_URL=http://127.0.0.1:1200 \
    CACHE_EXPIRE=60 \
    REQUEST_TIMEOUT=15000

VOLUME /data
EXPOSE 1200

ENTRYPOINT ["dumb-init", "--"]
CMD ["/opt/tweetalarm/start.sh"]

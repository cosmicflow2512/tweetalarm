FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    STATE_DIR=/data

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

VOLUME /data
CMD ["python", "/app/app.py"]

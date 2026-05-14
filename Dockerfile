FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY src ./src

# Persist SQLite by default; mount a volume at /data
RUN mkdir -p /data
ENV DATABASE_URL=sqlite+aiosqlite:////data/bot.db

WORKDIR /app/src

CMD ["python", "gnuchanos_bot.py"]

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip wheel "setuptools<81" \
    && python -m pip install -r /app/requirements.txt

COPY . /app

RUN mkdir -p /app/.runtime /app/models /app/reports /app/logs

CMD ["python", "run_trade_signal.py", "--mode", "shadow", "--once", "--config", "config/micro_near_v1_1m.json", "--model-path", "models/near_basis_qlearning.json", "--env-file", ".runtime/kucoin.env"]

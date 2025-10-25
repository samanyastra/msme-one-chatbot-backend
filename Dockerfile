FROM python:3.11-slim

# small defaults for predictable Python behavior
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5000 \
    WEB_CONCURRENCY=1

WORKDIR /app

# install minimal build deps (kept small) for wheels if required
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# copy app sources
COPY . /app
ENV PYTHONPATH=/app

EXPOSE ${PORT}

# Use gunicorn with the eventlet worker class so Flask-SocketIO works over websockets.
# Adjust WEB_CONCURRENCY as needed; eventlet handles concurrency cooperatively.
CMD ["gunicorn", "-k", "eventlet", "-w", "1", "run:app", "-b", "0.0.0.0:5000"]

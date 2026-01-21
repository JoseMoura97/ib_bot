FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
  && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY . /app

ENV PYTHONPATH=/app:/app/backend

RUN sed -i 's/\r$//' /app/backend/docker-entrypoint.sh && chmod +x /app/backend/docker-entrypoint.sh

ENTRYPOINT ["/bin/sh", "/app/backend/docker-entrypoint.sh"]
CMD ["celery", "-A", "app.worker.celery_app", "worker", "--loglevel=INFO"]

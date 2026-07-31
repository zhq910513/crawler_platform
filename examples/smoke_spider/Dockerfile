FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app
COPY runtime /tmp/crawler-runtime
RUN pip install --no-cache-dir /tmp/crawler-runtime
COPY examples/smoke_spider /app

CMD ["python", "-m", "crawler_runtime", "--entrypoint", "spiders.smoke_tasks:run", "--kwargs-json", "{}"]

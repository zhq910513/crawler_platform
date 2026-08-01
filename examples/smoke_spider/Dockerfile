FROM python:3.11-slim

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY runtime /tmp/crawler-runtime
RUN pip install --no-cache-dir /tmp/crawler-runtime
COPY examples/smoke_spider /app

CMD ["python", "-m", "crawler_runtime", "--entrypoint", "spiders.smoke_tasks:run", "--kwargs-json", "{}"]

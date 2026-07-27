FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

RUN find /etc/apt -type f \( -name "*.list" -o -name "*.sources" \) -exec sed -i \
        -e "s|deb.debian.org/debian|mirrors.tuna.tsinghua.edu.cn/debian|g" \
        -e "s|security.debian.org/debian-security|mirrors.tuna.tsinghua.edu.cn/debian-security|g" {} + \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY docker-entrypoint.sh /app/docker-entrypoint.sh
COPY app /app/app
RUN chmod +x /app/docker-entrypoint.sh \
    && mkdir -p /data/task-logs \
    && chown -R appuser:appuser /app /data/task-logs

USER appuser
EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

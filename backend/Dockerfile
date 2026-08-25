FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

RUN if [ -n "$APT_MIRROR" ]; then \
      if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i "s#http://deb.debian.org/debian#http://${APT_MIRROR}/debian#g; s#http://security.debian.org/debian-security#http://${APT_MIRROR}/debian-security#g" /etc/apt/sources.list.d/debian.sources; \
      elif [ -f /etc/apt/sources.list ]; then \
        sed -i "s#http://deb.debian.org/debian#http://${APT_MIRROR}/debian#g; s#http://security.debian.org/debian-security#http://${APT_MIRROR}/debian-security#g" /etc/apt/sources.list; \
      fi; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl tzdata git docker.io \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY alembic.ini /app/alembic.ini
COPY migrations /app/migrations
COPY app /app/app

RUN mkdir -p /data/task-logs /data/project-builds \
    && chown -R appuser:appuser /app /data/task-logs /data/project-builds

USER appuser
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

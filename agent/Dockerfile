FROM python:3.12-slim
WORKDIR /opt/crawler-agent
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt /opt/crawler-agent/requirements.txt
RUN pip install --no-cache-dir --upgrade pip -i ${PIP_INDEX_URL} \
    && pip install --no-cache-dir -i ${PIP_INDEX_URL} -r /opt/crawler-agent/requirements.txt
COPY crawler_agent /opt/crawler-agent/crawler_agent
CMD ["python", "-m", "crawler_agent.main"]

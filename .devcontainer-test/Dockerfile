FROM python:3.14-slim
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential && rm -rf /var/lib/apt/lists/*
COPY requirements_test.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements_test.txt
WORKDIR /work

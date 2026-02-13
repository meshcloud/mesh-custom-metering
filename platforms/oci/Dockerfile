FROM python:3.11-slim

WORKDIR /app

COPY src/core /app/core
COPY platforms/oci /app/platform

RUN pip install --no-cache-dir -r /app/core/requirements.txt && \
    pip install --no-cache-dir -r /app/platform/requirements.txt

ENV PYTHONUNBUFFERED=1

CMD ["python", "/app/platform/main.py"]

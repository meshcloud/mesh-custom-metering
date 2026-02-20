FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY platforms/aws/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY platforms/aws/main.py ./

# Create non-root user
RUN useradd -m -u 1000 metering && chown -R metering:metering /app
USER metering

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the metering collection
CMD ["python", "main.py"]

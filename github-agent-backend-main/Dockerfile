# Python backend application Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (git is required for repository cloning)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories for reports and logs
RUN mkdir -p /app/reports /app/logs

# Expose FastAPI port
EXPOSE 3000

# Default command (will be overridden by docker-compose)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3000"]

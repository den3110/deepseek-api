FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if required by curl_cffi or other packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies from requirements.txt and additional web frameworks
RUN pip install --no-cache-dir -r requirements.txt flask flask-cors python-dotenv

# Copy the rest of the application
COPY . .

# Expose the new port
EXPOSE 5024

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the server
CMD ["python", "chat_server.py"]

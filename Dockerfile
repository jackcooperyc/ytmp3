FROM python:3.10-slim

# Install ffmpeg for yt-dlp audio post-processing
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Start the application using gunicorn with a 120-second timeout for long downloads
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} --timeout 120 app:app"]

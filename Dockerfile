# VoxBox - Video to Obsidian Knowledge Pipeline
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Create non-root user
RUN useradd -m -u 1000 voxbox && \
    mkdir -p /app/data/Inbox /app/data/Outbox /app/data/Archive /app/data/Logs /app/data/tokens /app/data/temp && \
    chown -R voxbox:voxbox /app

# Install system dependencies (FFmpeg required for yt-dlp and faster-whisper)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ /app/src/

# Set proper permissions
RUN chown -R voxbox:voxbox /app

# Switch to non-root user
USER voxbox

# Expose OAuth callback port
EXPOSE 8080

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV DATA_DIR=/app/data

# Run the application
CMD ["python", "-m", "src.main"]


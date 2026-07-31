FROM python:3.13-slim

# Install FFmpeg
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY src/ ./src/
COPY web/ ./web/

# Create required directories
RUN mkdir -p segments originals logs

# Expose port
EXPOSE 8080

# Run server
CMD ["python3", "src/server.py"]

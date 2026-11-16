FROM python:3.11-slim

WORKDIR /app

# Install tzdata for accurate IANA timezone conversions across all 55 cities
RUN apt-get update && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY scraper /app/scraper
COPY run_scraper.py /app/run_scraper.py

VOLUME ["/app/data"]

# Default: run continuously every 1 hour (3600 seconds)
CMD ["python3", "run_scraper.py", "--output-dir", "/app/data", "--workers", "16", "--loop", "--interval-seconds", "3600"]

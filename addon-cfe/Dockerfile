FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    fonts-freefont-ttf \
    openssl \
    ca-certificates \
    libnss3 \
    libatk-bridge2.0-0 \
    libxss1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

COPY cfe_scraper.py .
COPY run.sh .
RUN chmod +x run.sh

CMD ["/app/run.sh"]
 

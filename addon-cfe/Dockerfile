FROM python:3.11-alpine

# Chromium en Alpine es mucho más ligero que en Debian
RUN apk add --no-cache \
    chromium \
    nss \
    freetype \
    harfbuzz \
    ttf-freefont

# Decirle a Playwright que use el Chromium del sistema
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/bin
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY cfe_scraper.py .
COPY run.sh .
RUN chmod +x run.sh

CMD ["/app/run.sh"]

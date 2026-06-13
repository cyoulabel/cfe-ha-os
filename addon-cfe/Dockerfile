ARG BUILD_FROM
FROM $BUILD_FROM

# Install system dependencies for Playwright/Chromium
RUN apk add --no-cache \
    python3 \
    py3-pip \
    chromium \
    chromium-chromedriver \
    nss \
    freetype \
    harfbuzz \
    ttf-freefont \
    font-noto-cjk \
    wqy-zenhei \
    && rm -rf /var/cache/apk/*

# Tell Playwright to use system Chromium instead of downloading its own
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/lib/chromium
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Install only Chromium for Playwright (no download, use system)
RUN python3 -m playwright install-deps chromium 2>/dev/null || true

COPY cfe_scraper.py .
COPY run.sh .
RUN chmod +x run.sh

CMD ["/app/run.sh"]

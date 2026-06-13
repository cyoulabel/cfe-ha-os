#!/usr/bin/with-contenv bashio

bashio::log.info "Iniciando CFE Addon..."
cd /app
exec python3 cfe_scraper.py

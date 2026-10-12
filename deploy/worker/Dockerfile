# Worker-servicen på Railway: kører skemalæggeren OG runneren, så pipelinen
# ikke længere afhænger af, at ejerens PC er tændt (OPS-010).
#
# Hvorfor Playwrights eget image frem for Railways standardbygning: agenterne
# scraper PCS med Chromium, og browseren skal følge med i imaget sammen med
# alle sine systembiblioteker. Versionen holdes i takt med playwright i
# requirements.txt — afviger de, starter Playwright ikke.
#
# API-servicen ("web") bruger IKKE denne fil. Den bygges som hidtil; kun
# worker-servicen har RAILWAY_DOCKERFILE_PATH sat til denne sti.
FROM mcr.microsoft.com/playwright/python:v1.59.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# `wait -n` kræver bash — derfor ikke /bin/sh.
CMD ["bash", "deploy/worker/start.sh"]

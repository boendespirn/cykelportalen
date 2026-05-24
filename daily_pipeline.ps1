# daily_pipeline.ps1
# Kører den daglige dataopdatering kl. 17:00 via Windows Task Scheduler.
# Sæt op: Opgavestyring → Opret opgave → Udløser: Dagligt 17:00
#          Handling: powershell.exe -ExecutionPolicy Bypass -File "C:\Users\jonas\Desktop\Cykelportalen\daily_pipeline.ps1"

$ErrorActionPreference = "Continue"
$ROOT = "C:\Users\jonas\Desktop\Cykelportalen"
$LOG  = "$ROOT\logs\pipeline_$(Get-Date -Format 'yyyyMMdd_HHmm').log"

# Sørg for log-mappe
if (-not (Test-Path "$ROOT\logs")) { New-Item -ItemType Directory "$ROOT\logs" | Out-Null }

function Log($msg) {
    $line = "$(Get-Date -Format 'HH:mm:ss') $msg"
    Write-Host $line
    Add-Content -Path $LOG -Value $line
}

Log "=== Klassementet daglig pipeline startet ==="

# 1. RSS-nyheder
Log "[1/4] Scraper RSS-nyheder..."
python "$ROOT\rss_news_scraper.py" 2>&1 | Tee-Object -Append $LOG
Log "[1/4] Faerdig."

# 2. AI-nyhedsbehandling (max 15 scores, max 4/uge publiceret)
Log "[2/4] AI-nyhedsbehandling..."
python "$ROOT\ai_news_processor.py" --limit 15 2>&1 | Tee-Object -Append $LOG
Log "[2/4] Faerdig."

# 3. Startlister (opdater for igangvaerende loeb)
Log "[3/4] Opdaterer startlister..."
python "$ROOT\startlist_agent.py" --update-status 2>&1 | Tee-Object -Append $LOG
Log "[3/4] Faerdig."

# 4. Social media posting (poster artikler med social_posted=false)
Log "[4/4] Social media posting..."
python "$ROOT\social_agent.py" 2>&1 | Tee-Object -Append $LOG
Log "[4/4] Faerdig."

Log "=== Pipeline faerdig ==="

# Behold kun de seneste 14 logfiler
Get-ChildItem "$ROOT\logs\pipeline_*.log" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 14 | Remove-Item -Force

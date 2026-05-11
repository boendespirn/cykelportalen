# Cykelportalen — CLAUDE.md

## Projektbeskrivelse
En dansk cykelportal der samler alt data om professionel cykling: løb, ryttere, hold, etaper, resultater, klassementer, udstyr og sponsorater. Portalen fungerer primært som en løbskalender med dybdegående bagvedliggende data.

**Målgruppe:** Cykelfans der søger information om kommende løb, rytterprofiler og historiske resultater.

---

## Arkitektur

```
cykel-frontend/     ← Next.js 16 + TypeScript + Tailwind CSS
api.py              ← FastAPI backend (Python)
race_agent.py       ← Scraper: UCI WorldTour fra VeloWire
stage_agent.py      ← Scraper: Etapedata
Supabase            ← PostgreSQL cloud database
```

**Deployments:**
- Frontend: Vercel (planlagt)
- Backend: Railway eller Render (planlagt)
- Database: Supabase (aktiv)

---

## Lokalt Dev-setup

### Frontend
```bash
cd cykel-frontend
npm install
npm run dev        # Kører på http://localhost:3000
```

### Backend
```bash
pip install fastapi uvicorn python-dotenv requests beautifulsoup4 python-slugify
uvicorn api:app --reload   # Kører på http://localhost:8000
```

### Scrapers
```bash
python race_agent.py    # Scraper UCI WorldTour løb fra VeloWire
python stage_agent.py   # Importer etapedata
python read_races.py    # Vis alle løb i databasen
```

---

## Environment Variables

Kræver `.env` fil i rod-mappen (ALDRIG commit denne):
```
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=xxx
```

---

## Database Schema (Supabase/PostgreSQL)

### Eksisterende tabeller
- `races` — løb (name, slug, start_date, end_date, country_code, category, source)
- `stages` — etaper (race_id, stage_number, name, date, distance_km, start_location, finish_location, elevation_gain_m, stage_type)

### Planlagte tabeller
- `riders` — rytterprofiler (name, nationality, dob, team_id, speciality)
- `teams` — hold (name, country, budget, sponsors)
- `results` — løbsresultater (race_id, rider_id, position, time, stage_number)
- `classifications` — klassementer (GC, points, mountains, youth)
- `equipment` — udstyr (brand, category, used_by_team_id)

---

## Data Sources

| Kilde | Hvad | Status |
|---|---|---|
| VeloWire | UCI WorldTour kalender | Aktiv |
| ProCyclingStats | Rytterprofiler, resultater | Planlagt |
| FirstCycling | Historiske data | Planlagt |
| PCS (ProCyclingStats) | Hold og sponsorer | Planlagt |
| UCI officielle | Officielle klassementer | Planlagt |

---

## Kodningskonventioner

- **Frontend:** TypeScript, dansk UI-tekst, Tailwind CSS, dark theme (slate-950, emerald accents)
- **Backend:** Python 3.10+, type hints, FastAPI, dansk kommentering OK
- **Database:** snake_case kolonnenavne, UUID primary keys
- **API:** REST, JSON responses, slugs til URL-identifikation af løb
- **Scrapers:** BeautifulSoup til statiske sider, Playwright til JS-tunge sider

---

## Vigtige kommandoer

```bash
# Kør type-check
cd cykel-frontend && npx tsc --noEmit

# Kør linting
cd cykel-frontend && npm run lint

# Byg frontend
cd cykel-frontend && npm run build

# Test API endpoint
curl http://localhost:8000/upcoming-races
```

---

## Kendte begrænsninger (ChatGPT-arv)
- Kun UCI WorldTour dækket (ingen CX, gravel, kvinder, U23)
- Ingen søgefunktion
- Ingen automatisk scheduler for scrapers
- Kun 2 test-etaper i databasen (TdF 2026)
- Country code er gæt baseret på løbsnavn (ikke officiel data)

# LSA Scraper + AI Caller

**Scrape Google Local Services Ads (sponsored listings) for any industry, then AI-call them to find businesses that miss after-hours calls.**

Works for: HVAC, Private Investigators, Plumbers, Electricians, Locksmiths, Lawyers — or add your own.

## The Pitch

> "I called your '24/7' emergency line at 2 AM last night and it went to voicemail. You likely lost a $1,500 job. We would have booked that for you."

---

## Setup (Any Machine)

```bash
git clone https://github.com/dyyldogg/lsa-scraper.git
cd lsa-scraper
chmod +x setup.sh && ./setup.sh
```

That installs everything: Python packages, Playwright, Chromium browser, and creates your `.env`.

### API Keys

Edit `.env` with the keys you need:

| What you're doing | Keys needed |
|---|---|
| **LSA Scraper only** | None — uses Playwright browser |
| **AI Caller** (Vapi) | `VAPI_API_KEY` + `VAPI_PHONE_ID` |
| **Legacy Maps scraper** | `RAPIDAPI_KEY` |

**Vapi.ai setup** (for the AI caller):
1. Sign up at [vapi.ai](https://vapi.ai)
2. Dashboard → API Keys → copy your key → paste as `VAPI_API_KEY`
3. Dashboard → Phone Numbers → import your Twilio number (or buy one)
4. Click the number → copy the ID → paste as `VAPI_PHONE_ID`

---

## Usage

### 1. Scrape LSA Leads (No API Key Needed)

```bash
# Scrape PI firms in one city
python3 -m nightline.cli lsa city pi "Los Angeles" CA

# Scrape across all LA metro cities
python3 -m nightline.cli lsa region pi los_angeles_metro

# Scrape across ALL of California
python3 -m nightline.cli lsa california pi

# Show the browser while scraping (for debugging)
python3 -m nightline.cli lsa city pi "San Diego" CA --visible

# List available industries and regions
python3 -m nightline.cli lsa industries
python3 -m nightline.cli lsa regions
```

**Supported industries:** `hvac`, `pi`, `plumber`, `electrician`, `locksmith`, `lawyer`

**California regions:** `los_angeles_metro`, `inland_empire`, `orange_county`, `san_diego`, `sf_bay_area`, `central_valley`

### 2. AI Call the Leads (Needs Vapi Key)

```bash
# Test with 1 call
python3 vapi_caller.py --test

# Call 10 leads
python3 vapi_caller.py --limit 10

# Call only businesses claiming 24/7 service
python3 vapi_caller.py --limit 50 --24-only

# Overnight autonomous mode (runs unattended, saves progress)
nohup python3 overnight_caller.py > overnight.log 2>&1 &
```

### 3. View Results

```bash
# List leads filtered by industry
python3 -m nightline.cli leads list --industry pi --sponsored

# Show qualified leads (didn't answer = sales opportunity)
python3 -m nightline.cli leads qualified --export leads.csv

# Stats
python3 -m nightline.cli leads stats

# Web dashboard
python3 -m nightline.cli dashboard
# → Open http://localhost:8000
```

### 4. Export for Google Sheets

```bash
# Export enriched call results
python3 export_enriched.py

# Results in data/overnight_ENRICHED_SHEETS.tsv (tab-separated, paste into Sheets)
# Qualified only: data/overnight_QUALIFIED_SHEETS.tsv
```

---

## How It Works

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  LSA Scraper     │     │  AI Caller       │     │  Results         │
│                  │     │                  │     │                  │
│  Playwright hits │ ──→ │  Vapi.ai calls   │ ──→ │  Voicemail?      │
│  Google LSA page │     │  each business   │     │  = QUALIFIED     │
│  for any industry│     │  at 2 AM         │     │  = Sales lead    │
│  in any city     │     │                  │     │                  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

**LSA Scraper:** Opens Google's Local Services Ads page in a headless browser, scrolls through results, and extracts business names, phone numbers, ratings, and Google Guaranteed status. These are the *sponsored* businesses — they're paying for ads, which means they have budget.

**AI Caller:** Uses Vapi.ai (GPT-3.5 + Deepgram voice) to call each business. The AI stays silent, navigates IVR menus, and classifies the result: human answered, voicemail, answering service, or no answer. Cost: ~$0.08/min per call.

**Qualification:** Businesses that go to voicemail or don't answer = qualified leads. They claim to be available but aren't. That's your pitch.

---

## Project Structure

```
├── setup.sh               # One-command setup
├── env.example             # All config vars documented
├── requirements.txt        # Python dependencies
│
├── nightline/
│   ├── config.py           # Industry configs, CA cities, all settings
│   ├── database.py         # SQLAlchemy models (Lead, CallAudit)
│   ├── lsa_scraper.py      # Playwright-based Google LSA scraper
│   ├── scraper.py          # Legacy Google Maps API scraper
│   ├── cli.py              # CLI commands (nightline lsa/scrape/call/leads)
│   └── dashboard.py        # FastAPI web dashboard
│
├── vapi_caller.py          # AI caller (interactive, single runs)
├── overnight_caller.py     # Autonomous overnight caller (unattended)
├── export_enriched.py      # Export call results for Google Sheets
└── data/                   # All output files (gitignored)
```

## Adding a New Industry

Edit `nightline/config.py` and add to the `INDUSTRIES` dict:

```python
INDUSTRIES = {
    "roofing": {
        "name": "Roofer",
        "lsa_queries": [
            "roofer",
            "roof repair",
            "emergency roof repair",
        ],
        "availability_keywords": [
            "24/7", "emergency", "same day",
        ],
    },
    # ... existing industries ...
}
```

Then scrape: `python3 -m nightline.cli lsa city roofing "Los Angeles" CA`

---

## License

MIT

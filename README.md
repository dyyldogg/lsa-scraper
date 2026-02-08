# 🌙 Nightline - AI-Powered Lead Generation

**Find businesses claiming 24/7 service that fail to answer the phone.**

Nightline automates the discovery and validation of high-value leads by:
1. **Scraping** businesses from Google Maps that advertise "24/7", "Emergency", or "Always Available" service
2. **Testing** their phone lines at various times to see if they actually answer
3. **Qualifying** leads that go to voicemail - these are your sales opportunities

## The Pitch

> "I called your '24/7' emergency line at 2 AM last night and it went to voicemail. You likely lost a $1,500 job. Nightline would have booked that for you."

## Quick Start

### 1. Install Dependencies

```bash
cd /Users/dylanrochex/Projects/HVAC_leads_googleads
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp env.example .env
# Edit .env with your API keys
```

Required API keys:
- **RapidAPI Key**: For Google Maps Local Business Data API
- **Twilio Credentials**: For automated phone calls (optional for mock mode)

### 3. Initialize Database

```bash
python main.py db init
```

### 4. Start Scraping Leads

```bash
# Scrape HVAC leads from a specific city
python main.py scrape city Denver CO --limit 50

# Or scrape multiple cities at once
python main.py scrape multi -c "Denver,CO;Phoenix,AZ;Dallas,TX"
```

### 5. Run Audit Calls

```bash
# Test mode (no real calls)
python main.py call audit --limit 10 --mock

# Live calls (requires Twilio)
python main.py call audit --limit 10
```

### 6. View Qualified Leads

```bash
# See leads that didn't answer (ready for sales!)
python main.py leads qualified

# Export to CSV
python main.py leads qualified --export leads.csv
```

## Web Dashboard

For a visual interface, run the web dashboard:

```bash
python run_dashboard.py
```

Then open http://localhost:8000 in your browser.

## CLI Commands

### Scraping

```bash
# Scrape a single city
nightline scrape city <CITY> <STATE> [--limit N]

# Scrape multiple cities
nightline scrape multi -c "City1,ST1;City2,ST2" [--limit N]
```

### Calling

```bash
# Run audit call batch
nightline call audit [--limit N] [--mock] [--all-leads]

# Call a specific lead
nightline call single <LEAD_ID> [--mock]
```

### Lead Management

```bash
# List all leads
nightline leads list [--status STATUS] [--city CITY] [--24-7]

# Show qualified leads (sales ready!)
nightline leads qualified [--export FILE.csv]

# Show statistics
nightline leads stats
```

### Database

```bash
# Initialize database
nightline db init

# Reset database (delete all data)
nightline db reset
```

## Configuration

### env.example → .env

```bash
# RapidAPI - Local Business Data (for Google Maps scraping)
RAPIDAPI_KEY=your_rapidapi_key_here

# Twilio Configuration (for automated calls)
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1234567890

# Optional: Your callback URL for Twilio webhooks
TWILIO_WEBHOOK_URL=https://your-domain.com/api/twilio/callback

# Database (defaults to SQLite)
DATABASE_URL=sqlite:///nightline.db
```

### Search Queries

Default search queries can be customized in `nightline/config.py`:

```python
DEFAULT_SEARCH_QUERIES = [
    "24/7 HVAC repair",
    "Emergency HVAC service",
    "24 hour furnace repair",
    "Emergency AC repair",
    "24/7 heating repair",
    "Emergency heating service",
    "After hours HVAC",
]
```

### Availability Keywords

Keywords used to detect 24/7 claims:

```python
AVAILABILITY_KEYWORDS = [
    "24/7",
    "24 hour",
    "24-hour",
    "around the clock",
    "always available",
    "emergency",
    "after hours",
    "nights and weekends",
    "open 24",
]
```

## Architecture

```
nightline/
├── __init__.py       # Package initialization
├── config.py         # Configuration management
├── database.py       # SQLAlchemy models (Lead, CallAudit, etc.)
├── scraper.py        # Google Maps scraping logic
├── caller.py         # Twilio calling automation
├── cli.py            # Command-line interface
└── dashboard.py      # FastAPI web dashboard
```

## Lead Lifecycle

```
NEW → SCHEDULED → CALLED → QUALIFIED/DISQUALIFIED → CONTACTED → CONVERTED
                              ↑                           ↑
                        Voicemail/No Answer        Sales outreach
                              ↓
                        GOLD MINE! 💰
```

## API Endpoints (Dashboard)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web dashboard |
| `/api/stats` | GET | Overall statistics |
| `/api/leads` | GET | List leads (with filters) |
| `/api/leads/qualified` | GET | Qualified leads only |
| `/api/leads/export` | GET | Export CSV |
| `/api/scrape` | POST | Start scraping job |
| `/api/calls/batch` | POST | Run call batch |
| `/api/lead/{id}` | GET | Single lead with history |
| `/api/twilio/callback` | POST | Twilio webhook |

## Workflow Example

### Daily Lead Generation

```bash
# Morning: Scrape new leads from target cities
python main.py scrape multi -c "Denver,CO;Phoenix,AZ;Dallas,TX" --limit 100

# Afternoon: Run audit calls (mock first to verify)
python main.py call audit --limit 20 --mock

# When ready for live calls:
python main.py call audit --limit 20

# Export qualified leads for sales team
python main.py leads qualified --export qualified_$(date +%Y%m%d).csv
```

### Multiple Time-of-Day Testing

For the most accurate results, test the same leads at different times:

```bash
# Evening test (7 PM)
python main.py call audit --limit 10

# Night test (scheduled via cron at 11 PM)
python main.py call audit --limit 10

# Weekend test
python main.py call audit --limit 10
```

## License

MIT License


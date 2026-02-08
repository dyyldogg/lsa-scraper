"""
Configuration management for Nightline.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# RapidAPI Configuration
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = "local-business-data.p.rapidapi.com"

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")
TWILIO_WEBHOOK_URL = os.getenv("TWILIO_WEBHOOK_URL", "")

# Vapi.ai Configuration (AI caller)
VAPI_API_KEY = os.getenv("VAPI_API_KEY", "")
VAPI_BASE_URL = "https://api.vapi.ai"
VAPI_PHONE_ID = os.getenv("VAPI_PHONE_ID", "")
VAPI_ASSISTANT_ID = os.getenv("VAPI_ASSISTANT_ID", "")  # Optional - auto-creates if empty

# Database
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'nightline.db'}")

# ═══════════════════════════════════════════════════════════════════════════════
# INDUSTRY CONFIGURATIONS
# ═══════════════════════════════════════════════════════════════════════════════
# Each industry defines the LSA search queries and availability keywords
# to look for. Add new industries here to expand coverage.

INDUSTRIES = {
    "hvac": {
        "name": "HVAC",
        "lsa_queries": [
            "hvac",
            "hvac repair",
            "air conditioning repair",
            "furnace repair",
            "heating repair",
            "emergency hvac",
        ],
        "availability_keywords": [
            "24/7", "24 hour", "24-hour", "around the clock",
            "always available", "emergency", "after hours",
            "nights and weekends", "open 24",
        ],
    },
    "pi": {
        "name": "Private Investigator",
        "lsa_queries": [
            "private investigator",
            "private detective",
            "investigation services",
            "surveillance services",
            "background check services",
            "PI near me",
        ],
        "availability_keywords": [
            "24/7", "24 hour", "24-hour", "around the clock",
            "always available", "emergency", "confidential",
            "discreet", "immediate",
        ],
    },
    "plumber": {
        "name": "Plumber",
        "lsa_queries": [
            "plumber",
            "plumbing repair",
            "emergency plumber",
            "drain cleaning",
            "water heater repair",
        ],
        "availability_keywords": [
            "24/7", "24 hour", "24-hour", "emergency",
            "after hours", "same day", "nights and weekends",
        ],
    },
    "electrician": {
        "name": "Electrician",
        "lsa_queries": [
            "electrician",
            "electrical repair",
            "emergency electrician",
            "electrical service",
        ],
        "availability_keywords": [
            "24/7", "24 hour", "24-hour", "emergency",
            "after hours", "same day",
        ],
    },
    "locksmith": {
        "name": "Locksmith",
        "lsa_queries": [
            "locksmith",
            "emergency locksmith",
            "lockout service",
            "lock repair",
        ],
        "availability_keywords": [
            "24/7", "24 hour", "24-hour", "emergency",
            "lockout", "immediate",
        ],
    },
    "lawyer": {
        "name": "Lawyer",
        "lsa_queries": [
            "personal injury lawyer",
            "criminal defense lawyer",
            "divorce lawyer",
            "immigration lawyer",
            "DUI lawyer",
        ],
        "availability_keywords": [
            "24/7", "free consultation", "available now",
            "emergency", "immediate",
        ],
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# CALIFORNIA CITIES (organized by region)
# ═══════════════════════════════════════════════════════════════════════════════

CALIFORNIA_CITIES = {
    "los_angeles_metro": [
        ("Los Angeles", "CA"),
        ("Long Beach", "CA"),
        ("Santa Monica", "CA"),
        ("Pasadena", "CA"),
        ("Glendale", "CA"),
        ("Burbank", "CA"),
        ("Torrance", "CA"),
        ("Inglewood", "CA"),
        ("Downey", "CA"),
        ("Pomona", "CA"),
        ("West Hollywood", "CA"),
    ],
    "inland_empire": [
        ("Riverside", "CA"),
        ("San Bernardino", "CA"),
        ("Ontario", "CA"),
        ("Rancho Cucamonga", "CA"),
        ("Fontana", "CA"),
        ("Moreno Valley", "CA"),
    ],
    "orange_county": [
        ("Anaheim", "CA"),
        ("Santa Ana", "CA"),
        ("Irvine", "CA"),
        ("Huntington Beach", "CA"),
        ("Fullerton", "CA"),
        ("Costa Mesa", "CA"),
    ],
    "san_diego": [
        ("San Diego", "CA"),
        ("Chula Vista", "CA"),
        ("Oceanside", "CA"),
        ("Escondido", "CA"),
        ("Carlsbad", "CA"),
    ],
    "sf_bay_area": [
        ("San Francisco", "CA"),
        ("San Jose", "CA"),
        ("Oakland", "CA"),
        ("Fremont", "CA"),
        ("Berkeley", "CA"),
        ("Palo Alto", "CA"),
        ("Santa Clara", "CA"),
    ],
    "central_valley": [
        ("Fresno", "CA"),
        ("Bakersfield", "CA"),
        ("Sacramento", "CA"),
        ("Stockton", "CA"),
        ("Modesto", "CA"),
        ("Visalia", "CA"),
    ],
}

# Flatten all California cities into a single list
ALL_CALIFORNIA_CITIES = []
for region_cities in CALIFORNIA_CITIES.values():
    ALL_CALIFORNIA_CITIES.extend(region_cities)


def get_industry_config(industry_key: str) -> dict:
    """Get configuration for a specific industry."""
    industry = INDUSTRIES.get(industry_key.lower())
    if not industry:
        available = ", ".join(INDUSTRIES.keys())
        raise ValueError(f"Unknown industry '{industry_key}'. Available: {available}")
    return industry


def get_cities_for_region(region: str) -> list:
    """Get cities for a specific California region."""
    cities = CALIFORNIA_CITIES.get(region)
    if not cities:
        available = ", ".join(CALIFORNIA_CITIES.keys())
        raise ValueError(f"Unknown region '{region}'. Available: {available}")
    return cities


# ═══════════════════════════════════════════════════════════════════════════════
# LEGACY DEFAULTS (backward compatibility with existing HVAC scraper)
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_SEARCH_QUERIES = INDUSTRIES["hvac"]["lsa_queries"]
AVAILABILITY_KEYWORDS = INDUSTRIES["hvac"]["availability_keywords"]

# Call audit settings
CALL_TIMEOUT_SECONDS = 30  # How long to let the phone ring
VOICEMAIL_DETECTION_TIMEOUT = 10  # Seconds to wait for voicemail detection

# LSA Scraper settings
LSA_PAGE_LOAD_TIMEOUT = 30000  # ms - how long to wait for LSA page to load
LSA_SCROLL_DELAY = 1.5  # seconds between scrolls to load more results
LSA_MAX_SCROLLS = 15  # maximum scroll attempts to load all results


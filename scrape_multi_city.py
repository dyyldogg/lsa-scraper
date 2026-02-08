#!/usr/bin/env python3
"""
Multi-City HVAC Lead Scraper
Scrapes businesses across major US metro areas using RapidAPI.
Smart zip code spacing to maximize coverage without duplicates.
"""
import os
import json
import csv
import time
import requests
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path("data")
OUTPUT_DIR.mkdir(exist_ok=True)

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "769cd3d089msh9577ad89e236d72p198215jsnfeab8ea24465")
RAPIDAPI_HOST = "local-business-data.p.rapidapi.com"

# Strategic metro areas with spaced-out zip codes for max coverage
# Each city has 2-3 zip codes spread across different areas
METRO_AREAS = [
    # California
    {"city": "Los Angeles", "state": "CA", "zips": ["90001", "90210", "91301"]},
    {"city": "San Diego", "state": "CA", "zips": ["92101", "92129"]},
    {"city": "San Francisco", "state": "CA", "zips": ["94102", "94536"]},
    
    # Texas - huge HVAC market (hot climate)
    {"city": "Houston", "state": "TX", "zips": ["77001", "77070", "77459"]},
    {"city": "Dallas", "state": "TX", "zips": ["75201", "75287", "75080"]},
    {"city": "Austin", "state": "TX", "zips": ["78701", "78759"]},
    {"city": "San Antonio", "state": "TX", "zips": ["78201", "78258"]},
    
    # Arizona - hot climate = high HVAC demand
    {"city": "Phoenix", "state": "AZ", "zips": ["85001", "85254", "85048"]},
    {"city": "Tucson", "state": "AZ", "zips": ["85701", "85750"]},
    
    # Florida - hot/humid = year-round HVAC
    {"city": "Miami", "state": "FL", "zips": ["33101", "33180", "33155"]},
    {"city": "Orlando", "state": "FL", "zips": ["32801", "32819"]},
    {"city": "Tampa", "state": "FL", "zips": ["33601", "33647"]},
    {"city": "Jacksonville", "state": "FL", "zips": ["32202", "32256"]},
    
    # Georgia
    {"city": "Atlanta", "state": "GA", "zips": ["30301", "30327", "30093"]},
    
    # Nevada
    {"city": "Las Vegas", "state": "NV", "zips": ["89101", "89134", "89052"]},
    
    # Colorado
    {"city": "Denver", "state": "CO", "zips": ["80202", "80237", "80123"]},
    
    # North Carolina
    {"city": "Charlotte", "state": "NC", "zips": ["28202", "28277"]},
    {"city": "Raleigh", "state": "NC", "zips": ["27601", "27615"]},
    
    # Tennessee
    {"city": "Nashville", "state": "TN", "zips": ["37201", "37215"]},
    
    # Illinois
    {"city": "Chicago", "state": "IL", "zips": ["60601", "60614", "60618"]},
    
    # New York Metro
    {"city": "New York", "state": "NY", "zips": ["10001", "10028", "11201"]},
    
    # Pennsylvania
    {"city": "Philadelphia", "state": "PA", "zips": ["19102", "19128"]},
    
    # Washington
    {"city": "Seattle", "state": "WA", "zips": ["98101", "98115"]},
    
    # Massachusetts
    {"city": "Boston", "state": "MA", "zips": ["02101", "02134"]},
]


def search_hvac_businesses(city: str, state: str, zip_code: str, limit: int = 20) -> list:
    """Search for HVAC businesses in a location."""
    
    url = "https://local-business-data.p.rapidapi.com/search"
    
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST
    }
    
    params = {
        "query": f"HVAC repair near {zip_code} {city} {state}",
        "limit": str(limit),
        "region": "us",
        "language": "en"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            return data.get("data", [])
        elif response.status_code == 429:
            print(f"      ⚠️ Rate limited, waiting 10s...")
            time.sleep(10)
            return search_hvac_businesses(city, state, zip_code, limit)
        else:
            print(f"      ❌ Error {response.status_code}")
            return []
            
    except Exception as e:
        print(f"      ❌ Exception: {e}")
        return []


def format_phone(phone: str) -> str:
    """Format phone to +1XXXXXXXXXX."""
    if not phone:
        return None
    digits = ''.join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return None


def main():
    print("\n" + "="*70)
    print("🌎 MULTI-CITY HVAC LEAD SCRAPER")
    print("   Targeting businesses currently advertising on Google")
    print("="*70)
    
    all_leads = []
    seen_phones = set()
    seen_names = set()
    
    total_metros = len(METRO_AREAS)
    
    for i, metro in enumerate(METRO_AREAS, 1):
        city = metro["city"]
        state = metro["state"]
        zips = metro["zips"]
        
        print(f"\n[{i}/{total_metros}] 📍 {city}, {state}")
        
        metro_leads = []
        
        for zip_code in zips:
            print(f"   → Searching {zip_code}...", end=" ", flush=True)
            
            businesses = search_hvac_businesses(city, state, zip_code)
            
            new_count = 0
            for biz in businesses:
                phone = format_phone(biz.get("phone_number"))
                name = biz.get("name", "")
                
                # Dedupe by phone AND name (some businesses have multiple locations)
                name_key = name.lower().replace(" ", "").replace("&", "and")[:20]
                
                if phone and phone not in seen_phones and name_key not in seen_names:
                    seen_phones.add(phone)
                    seen_names.add(name_key)
                    
                    # Check for 24 hours in working hours
                    hours = biz.get("working_hours", {})
                    is_24h = False
                    if hours:
                        for day, time_str in hours.items():
                            if "24" in str(time_str).lower() or "open 24" in str(time_str).lower():
                                is_24h = True
                                break
                    
                    lead = {
                        "name": name,
                        "phone": phone,
                        "address": biz.get("full_address", ""),
                        "city": city,
                        "state": state,
                        "zip": zip_code,
                        "rating": biz.get("rating"),
                        "reviews": biz.get("review_count"),
                        "is_24_hours": is_24h,
                        "website": biz.get("website", ""),
                        "google_id": biz.get("business_id", "")
                    }
                    metro_leads.append(lead)
                    all_leads.append(lead)
                    new_count += 1
            
            print(f"+{new_count} leads")
            time.sleep(0.5)  # Small delay between requests
        
        print(f"   ✅ {city}: {len(metro_leads)} unique leads")
    
    # Save results
    if all_leads:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # CSV
        csv_file = OUTPUT_DIR / f"hvac_multi_city_{timestamp}.csv"
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=all_leads[0].keys())
            writer.writeheader()
            writer.writerows(all_leads)
        
        # JSON
        json_file = OUTPUT_DIR / f"hvac_multi_city_{timestamp}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(all_leads, f, indent=2)
        
        # Phone list for calling (24/7 businesses first)
        phones_file = OUTPUT_DIR / f"hvac_multi_city_{timestamp}_phones.txt"
        
        # Sort: 24/7 businesses first
        sorted_leads = sorted(all_leads, key=lambda x: (not x["is_24_hours"], x["city"]))
        
        with open(phones_file, 'w') as f:
            f.write("# 24/7 BUSINESSES (Priority Targets)\n")
            for lead in sorted_leads:
                if lead["is_24_hours"]:
                    f.write(f"{lead['phone']}\t{lead['name']}\t{lead['city']}, {lead['state']}\n")
            
            f.write("\n# OTHER BUSINESSES\n")
            for lead in sorted_leads:
                if not lead["is_24_hours"]:
                    f.write(f"{lead['phone']}\t{lead['name']}\t{lead['city']}, {lead['state']}\n")
        
        # Stats
        print(f"\n{'='*70}")
        print(f"✅ SCRAPING COMPLETE!")
        print(f"{'='*70}")
        print(f"   📊 Total unique leads: {len(all_leads)}")
        print(f"   🕐 Claiming 24/7: {len([l for l in all_leads if l['is_24_hours']])}")
        print(f"   🏙️  Cities covered: {len(METRO_AREAS)}")
        
        print(f"\n💾 Files saved:")
        print(f"   📄 {csv_file}")
        print(f"   📄 {json_file}")
        print(f"   📞 {phones_file}")
        
        # Top cities by lead count
        from collections import Counter
        city_counts = Counter(l["city"] for l in all_leads)
        print(f"\n📈 Top cities by lead count:")
        for city, count in city_counts.most_common(5):
            print(f"   • {city}: {count}")
    
    else:
        print("\n❌ No leads found")


if __name__ == "__main__":
    main()


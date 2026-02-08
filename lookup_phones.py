#!/usr/bin/env python3
"""
Lookup phone numbers for businesses using RapidAPI Local Business Data.
Takes business names from LSA page and enriches with contact info.
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

# RapidAPI configuration
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "769cd3d089msh9577ad89e236d72p198215jsnfeab8ea24465")
RAPIDAPI_HOST = "local-business-data.p.rapidapi.com"

# Businesses from LSA page (Los Angeles HVAC - these are ACTIVELY ADVERTISING)
LSA_BUSINESSES = [
    {"name": "Affordable Heating and Air", "rating": 4.9, "reviews": 1039, "is_24h": False},
    {"name": "American AC Heat Plumbing", "rating": 4.9, "reviews": 3296, "is_24h": True},
    {"name": "Kahn Air Conditioning", "rating": 4.9, "reviews": 1583, "is_24h": True},
    {"name": "So Cal Plumbing Heating and Air Conditioning", "rating": 4.9, "reviews": 196, "is_24h": False},
    {"name": "Lions Heating & Air Conditioning", "rating": 4.9, "reviews": 219, "is_24h": False},
    {"name": "Service Genius", "rating": 5.0, "reviews": 447, "is_24h": False},
    {"name": "Service Champions Los Angeles HVAC", "rating": 4.9, "reviews": 667, "is_24h": True},
    {"name": "Southland Heating & Air Conditioning", "rating": 4.9, "reviews": 1674, "is_24h": False},
    {"name": "Air Quality Pros USA", "rating": 4.9, "reviews": 575, "is_24h": True},
    {"name": "Rowland Air Conditioning and Heating", "rating": 4.9, "reviews": 1790, "is_24h": True},
    {"name": "Zephyr Heating & Air Conditioning", "rating": 5.0, "reviews": 449, "is_24h": True},
    {"name": "Dutton Heating & Air", "rating": 4.7, "reviews": 2764, "is_24h": True},
    {"name": "Southwest HVAC", "rating": 4.9, "reviews": 303, "is_24h": False},
    {"name": "Downey Plumbing Heating and Air Conditioning", "rating": 4.7, "reviews": 467, "is_24h": False},
    {"name": "Monkey Wrench Plumbing Heating Air Electric", "rating": 4.8, "reviews": 464, "is_24h": True},
    {"name": "AZ Air Conditioning and Heating", "rating": 4.8, "reviews": 3169, "is_24h": True},
    {"name": "Garcia Air Systems", "rating": 5.0, "reviews": 35, "is_24h": False},
    {"name": "Absolute Airflow Inc", "rating": 4.8, "reviews": 4311, "is_24h": True},
    {"name": "Airplus of California Inc", "rating": 4.9, "reviews": 1320, "is_24h": True},
    {"name": "JW Plumbing Heating & Air", "rating": 4.8, "reviews": 2531, "is_24h": True},
]


def search_business(business_name: str, city: str = "Los Angeles", state: str = "CA") -> dict:
    """Search for a business and return details including phone number."""
    
    url = "https://local-business-data.p.rapidapi.com/search"
    
    query = f"{business_name} {city} {state}"
    
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST
    }
    
    params = {
        "query": query,
        "limit": "1",
        "region": "us",
        "language": "en"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("data") and len(data["data"]) > 0:
                biz = data["data"][0]
                return {
                    "name": biz.get("name"),
                    "phone": biz.get("phone_number"),
                    "address": biz.get("full_address"),
                    "rating": biz.get("rating"),
                    "reviews": biz.get("review_count"),
                    "website": biz.get("website"),
                    "google_id": biz.get("business_id")
                }
        elif response.status_code == 429:
            print(f"   ⚠️ Rate limited. Waiting 5s...")
            time.sleep(5)
            return search_business(business_name, city, state)  # Retry
        else:
            print(f"   ❌ Error {response.status_code}: {response.text[:100]}")
            
    except Exception as e:
        print(f"   ❌ Exception: {e}")
    
    return None


def main():
    print("\n" + "="*60)
    print("🔍 HVAC Lead Phone Number Lookup")
    print("   Using RapidAPI Local Business Data")
    print("="*60)
    
    enriched = []
    
    print(f"\n📋 Looking up {len(LSA_BUSINESSES)} businesses from LSA...\n")
    
    for i, biz in enumerate(LSA_BUSINESSES, 1):
        print(f"{i}. {biz['name']}...", end=" ", flush=True)
        
        result = search_business(biz["name"])
        
        if result and result.get("phone"):
            phone = result["phone"]
            # Format phone number
            if not phone.startswith("+"):
                digits = ''.join(c for c in phone if c.isdigit())
                if len(digits) == 10:
                    phone = f"+1{digits}"
                elif len(digits) == 11 and digits.startswith("1"):
                    phone = f"+{digits}"
            
            enriched.append({
                "name": biz["name"],
                "phone": phone,
                "address": result.get("address", ""),
                "rating": biz["rating"],
                "reviews": biz["reviews"],
                "is_24_hours": biz["is_24h"],
                "website": result.get("website", ""),
                "source": "LSA - Los Angeles",
                "advertising": True
            })
            print(f"✅ {phone}")
        else:
            print("❌ No phone found")
        
        # Small delay to avoid rate limiting
        time.sleep(0.5)
    
    # Save results
    if enriched:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # CSV
        csv_file = OUTPUT_DIR / f"hvac_lsa_leads_{timestamp}.csv"
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=enriched[0].keys())
            writer.writeheader()
            writer.writerows(enriched)
        
        # JSON
        json_file = OUTPUT_DIR / f"hvac_lsa_leads_{timestamp}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(enriched, f, indent=2)
        
        # Phone list for calling
        phones_file = OUTPUT_DIR / f"hvac_lsa_leads_{timestamp}_phones.txt"
        with open(phones_file, 'w') as f:
            for b in enriched:
                f.write(f"{b['phone']}\t{b['name']}\t{'24/7' if b['is_24_hours'] else ''}\n")
        
        print(f"\n{'='*60}")
        print(f"✅ SUCCESS!")
        print(f"{'='*60}")
        print(f"   Total leads with phones: {len(enriched)}")
        print(f"   Claiming 24/7: {len([b for b in enriched if b['is_24_hours']])}")
        print(f"\n💾 Saved to:")
        print(f"   📄 {csv_file}")
        print(f"   📞 {phones_file}")
        
        # Show sample
        print(f"\n📊 Sample leads (24/7 businesses):")
        for b in enriched[:5]:
            if b["is_24_hours"]:
                print(f"   • {b['name']}: {b['phone']}")
    else:
        print("\n❌ No leads found with phone numbers")


if __name__ == "__main__":
    main()


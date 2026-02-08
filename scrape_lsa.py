#!/usr/bin/env python3
"""
Google Local Services Ads Scraper
Extracts phone numbers from HVAC businesses running Google Ads.

Strategy: Start from Google search, then extract from the sponsored local services section.
"""
import argparse
import asyncio
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict
from playwright.async_api import async_playwright

OUTPUT_DIR = Path("data")
OUTPUT_DIR.mkdir(exist_ok=True)


def clean_phone(phone: str) -> str:
    """Clean and format phone number to +1XXXXXXXXXX format."""
    if not phone:
        return None
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith('1'):
        return f"+{digits}"
    return None


async def scrape_via_google_search(
    city: str = "Los Angeles",
    state: str = "CA",
    service: str = "hvac repair",
    headless: bool = True,
    max_results: int = 50
) -> List[Dict]:
    """
    Scrape by going through Google search first.
    """
    businesses = []
    seen_phones = set()
    
    search_query = f"{service} near {city} {state}"
    url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}"
    
    print(f"\n🔍 Scraping Google Local Services")
    print(f"   Search: {search_query}")
    print(f"   Headless: {headless}\n")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        
        context = await browser.new_context(
            viewport={"width": 1200, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="en-US"
        )
        
        page = await context.new_page()
        
        try:
            print("📄 Loading Google search...")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            
            # Take screenshot for debugging
            await page.screenshot(path=OUTPUT_DIR / "step1_search.png")
            
            # Look for "More businesses" or "Show more" to expand
            try:
                more_btn = await page.query_selector('text="More businesses"')
                if more_btn:
                    await more_btn.click()
                    await asyncio.sleep(2)
            except:
                pass
            
            # Now get the page content
            html = await page.content()
            text = await page.inner_text("body")
            
            # Save raw text for debugging
            with open(OUTPUT_DIR / "debug_text.txt", "w") as f:
                f.write(text)
            
            print("📞 Extracting phone numbers...")
            
            # Find all phone number patterns in the text
            phone_pattern = r'\((\d{3})\)\s*(\d{3})[-.\s]?(\d{4})'
            
            # Split text into chunks to associate phones with business names
            lines = text.split('\n')
            
            current_business = None
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                
                # Check if this line contains a phone number
                phone_match = re.search(phone_pattern, line)
                if phone_match:
                    phone = clean_phone(phone_match.group(0))
                    if phone and phone not in seen_phones:
                        # Look backward for business name
                        name = None
                        rating = None
                        reviews = None
                        
                        # Search backwards for the business name
                        for j in range(i-1, max(0, i-15), -1):
                            prev = lines[j].strip()
                            if not prev:
                                continue
                            
                            # Skip common non-name patterns
                            skip_patterns = [
                                'Get phone', 'Book', 'Message', 'Share', 'Sponsored',
                                'Open', 'Closes', 'hours', 'HVAC Pro', 'years in business',
                                'Serves', 'Free estimate', 'Reviews', 'Website', 'Directions'
                            ]
                            if any(p.lower() in prev.lower() for p in skip_patterns):
                                continue
                            
                            # Check for rating pattern
                            rating_match = re.match(r'^(\d\.\d)\s*[★☆·]', prev)
                            if rating_match:
                                rating = float(rating_match.group(1))
                                rev_match = re.search(r'\(([\d,]+)\)', prev)
                                if rev_match:
                                    reviews = int(rev_match.group(1).replace(',', ''))
                                continue
                            
                            # This might be the business name
                            # Names typically start with capital letter, have multiple words
                            if (re.match(r'^[A-Z]', prev) and 
                                len(prev) > 3 and 
                                not re.match(r'^[\d\.\s]+$', prev)):
                                name = prev
                                break
                        
                        if name:
                            seen_phones.add(phone)
                            
                            # Check context for 24 hours
                            context_start = max(0, i-10)
                            context_text = '\n'.join(lines[context_start:i+3]).lower()
                            is_24h = 'open 24' in context_text or '24 hour' in context_text
                            
                            businesses.append({
                                'name': name,
                                'phone': phone,
                                'rating': rating,
                                'reviews': reviews,
                                'is_24_hours': is_24h,
                                'source': f"{city}, {state}"
                            })
                            print(f"   ✅ {name}: {phone}")
            
            # Also try to extract from the local services cards specifically
            print("\n📋 Checking sponsored section...")
            
            # Find local services cards
            cards = await page.query_selector_all('[data-attrid="local_card"]')
            if not cards:
                cards = await page.query_selector_all('.rllt__details')
            if not cards:
                cards = await page.query_selector_all('[data-local-attribute]')
            
            print(f"   Found {len(cards)} local service cards")
            
            for card in cards[:max_results]:
                try:
                    card_text = await card.inner_text()
                    
                    # Look for phone in card
                    phone_match = re.search(phone_pattern, card_text)
                    if phone_match:
                        phone = clean_phone(phone_match.group(0))
                        if phone and phone not in seen_phones:
                            # First non-empty line is usually the name
                            lines = [l.strip() for l in card_text.split('\n') if l.strip()]
                            name = lines[0] if lines else "Unknown"
                            
                            seen_phones.add(phone)
                            businesses.append({
                                'name': name,
                                'phone': phone,
                                'rating': None,
                                'reviews': None,
                                'is_24_hours': 'open 24' in card_text.lower(),
                                'source': f"{city}, {state}"
                            })
                            print(f"   ✅ {name}: {phone}")
                except:
                    continue
            
            # Final screenshot
            await page.screenshot(path=OUTPUT_DIR / "step2_final.png")
            print(f"\n   📸 Screenshots saved to {OUTPUT_DIR}/")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path=OUTPUT_DIR / "error_screenshot.png")
        finally:
            await browser.close()
    
    return businesses


def save_results(businesses: List[Dict], prefix: str = "hvac_leads"):
    """Save results to files."""
    if not businesses:
        print("\n❌ No businesses found")
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # CSV
    csv_file = OUTPUT_DIR / f"{prefix}_{timestamp}.csv"
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'phone', 'rating', 'reviews', 'is_24_hours', 'source'])
        writer.writeheader()
        writer.writerows(businesses)
    
    # JSON
    json_file = OUTPUT_DIR / f"{prefix}_{timestamp}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(businesses, f, indent=2)
    
    # Phone list
    phones_file = OUTPUT_DIR / f"{prefix}_{timestamp}_phones.txt"
    with open(phones_file, 'w') as f:
        for b in businesses:
            f.write(f"{b['phone']}\t{b['name']}\n")
    
    print(f"\n💾 Saved {len(businesses)} leads:")
    print(f"   {csv_file}")
    print(f"   {phones_file}")


async def main():
    parser = argparse.ArgumentParser(description="Scrape Google LSA")
    parser.add_argument("--city", default="Los Angeles", help="City name")
    parser.add_argument("--state", default="CA", help="State")  
    parser.add_argument("--service", default="hvac repair", help="Service to search")
    parser.add_argument("--visible", action="store_true", help="Show browser")
    parser.add_argument("--max", type=int, default=50, help="Max results")
    
    args = parser.parse_args()
    
    businesses = await scrape_via_google_search(
        city=args.city,
        state=args.state,
        service=args.service,
        headless=not args.visible,
        max_results=args.max
    )
    
    save_results(businesses, f"hvac_{args.city.lower().replace(' ', '_')}")
    
    print(f"\n{'='*50}")
    print(f"📊 Total: {len(businesses)} businesses with phone numbers")
    if businesses:
        with_24h = len([b for b in businesses if b.get('is_24_hours')])
        print(f"   Claiming 24/7: {with_24h}")


if __name__ == "__main__":
    asyncio.run(main())

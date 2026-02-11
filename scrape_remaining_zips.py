#!/usr/bin/env python3
"""
Helper script to extract and save business listings from browser snapshots.
Used during manual scraping workflow.
"""
import csv
from datetime import datetime
import re
import sys

def parse_business(text, zip_code, location):
    if not text or len(text) < 15:
        return None
    
    name_match = re.match(r'^(.+?)\s*\([\d,]+\)', text)
    if not name_match:
        return None
    name = name_match.group(1).strip()
    
    reviews_match = re.search(r'\(([\d,]+)\)', text)
    reviews = int(reviews_match.group(1).replace(',', '')) if reviews_match else 0
    
    years_match = re.search(r'(\d+\+?)\s*years?\s*in\s*business', text)
    years = years_match.group(1) if years_match else ''
    
    open_24h = 'Open 24 hours' in text
    
    if 'Open 24 hours' in text:
        hours = 'Open 24 hours'
    elif 'Closed' in text:
        hours_match = re.search(r'(Closed[^\n]{0,50})', text)
        hours = hours_match.group(1).strip() if hours_match else 'Closed'
    elif 'Closes soon' in text:
        hours_match = re.search(r'(Closes soon[^\n]{0,50})', text)
        hours = hours_match.group(1).strip() if hours_match else 'Closes soon'
    else:
        hours = ''
    
    serves_match = re.search(r'Serves\s+([A-Za-z\s.]+?)(?=\s+(?:Open|Closed|Closes))', text)
    serves = serves_match.group(1).strip() if serves_match else ''
    
    return {
        'name': name,
        'reviews': reviews,
        'years_in_business': years,
        'open_24h': open_24h,
        'hours': hours,
        'serves': serves,
        'zip_code': zip_code,
        'location': location,
        'scraped_at': datetime.now().strftime('%Y-%m-%d')
    }

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: python scrape_remaining_zips.py <zip_code> <location> <business1> <business2> ...")
        sys.exit(1)
    
    zip_code = sys.argv[1]
    location = sys.argv[2]
    businesses = sys.argv[3:]
    
    csv_file = 'data/pi_lawyers_lsa_scrape.csv'
    
    parsed_businesses = []
    for biz_text in businesses:
        parsed = parse_business(biz_text, zip_code, location)
        if parsed:
            parsed_businesses.append(parsed)
    
    fieldnames = ['name', 'reviews', 'years_in_business', 'open_24h', 'hours', 'serves', 'zip_code', 'location', 'scraped_at']
    with open(csv_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        for biz in parsed_businesses:
            writer.writerow(biz)
    
    print(f'Added {len(parsed_businesses)} businesses for {location} ({zip_code})')

#!/usr/bin/env python3
"""
Convert pi_lawyers_lsa_scrape.csv to Apollo.io import format
"""
import csv
import re

def parse_location(location_str):
    """Parse 'City, State' into city and state"""
    if ',' in location_str:
        parts = location_str.split(',')
        city = parts[0].strip()
        state = parts[1].strip() if len(parts) > 1 else ''
        return city, state
    return location_str.strip(), ''

def convert_to_apollo(input_file, output_file):
    """Convert the scraped data to Apollo format"""
    
    apollo_rows = []
    
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            city, state = parse_location(row['location'])
            
            apollo_row = {
                'First Name': '',  # Not available
                'Last Name': '',   # Not available
                'Email': '',       # Not available
                'Phone': '',       # Not available
                'Company Name': row['name'],
                'Title': 'Personal Injury Lawyer',  # Inferred
                'City': city,
                'State': state,
                'ZIP Code': row['zip_code'],
                'Website': '',     # Not available
                'Industry': 'Legal Services',
                'Company Size': '',  # Not available
                'LinkedIn Company URL': '',  # Not available
                'Notes': f"Reviews: {row['reviews']}, Years in business: {row['years_in_business']}, Open 24h: {row['open_24h']}, Serves: {row['serves']}"
            }
            
            apollo_rows.append(apollo_row)
    
    # Write Apollo CSV
    fieldnames = [
        'First Name', 'Last Name', 'Email', 'Phone', 'Company Name', 'Title',
        'City', 'State', 'ZIP Code', 'Website', 'Industry', 'Company Size',
        'LinkedIn Company URL', 'Notes'
    ]
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(apollo_rows)
    
    print(f"✓ Converted {len(apollo_rows)} records")
    print(f"✓ Output saved to: {output_file}")
    print(f"\nNote: Phone numbers and emails were not collected during scraping.")
    print(f"Apollo can enrich these records with contact information.")

if __name__ == '__main__':
    convert_to_apollo(
        'data/pi_lawyers_lsa_scrape.csv',
        'data/apollo_import_pi_lawyers.csv'
    )

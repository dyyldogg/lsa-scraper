#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export enriched call results with full business info."""

import json
import csv
import os
import requests
from datetime import datetime, timezone, timedelta

VAPI_API_KEY = os.environ.get('VAPI_API_KEY', 'd6dc0c9c-3cc7-40f7-a67f-16daea564e84')
DATA_DIR = '/Users/dylanrochex/Projects/HVAC_leads_googleads/data'

def main():
    # Load all calls from Vapi
    print("Fetching calls from Vapi...")
    resp = requests.get(
        "https://api.vapi.ai/call?limit=500",
        headers={"Authorization": f"Bearer {VAPI_API_KEY}"}
    )
    calls = resp.json()
    print(f"Got {len(calls)} calls")
    
    # Load the full lead data
    leads_by_phone = {}
    lead_file = os.path.join(DATA_DIR, 'hvac_multi_city_20260204_151436.csv')
    with open(lead_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            phone = row.get('phone', '').strip()
            # Normalize phone to last 10 digits
            phone_clean = ''.join(c for c in phone if c.isdigit())[-10:]
            if phone_clean:
                leads_by_phone[phone_clean] = row
    
    print(f"Loaded {len(leads_by_phone)} leads from CSV")
    
    # PST timezone
    pst = timezone(timedelta(hours=-8))
    
    enriched = []
    for c in calls:
        # Get phone from customer object
        phone_raw = c.get('customer', {}).get('number', '')
        if not phone_raw:
            continue
        
        phone_clean = ''.join(ch for ch in phone_raw if ch.isdigit())[-10:]
        
        # Find matching lead
        lead = leads_by_phone.get(phone_clean, {})
        if not lead:
            continue  # Skip calls not in our lead list
        
        # Parse timestamp
        created = c.get('createdAt', '')
        if created:
            try:
                dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                call_time = dt.astimezone(pst).strftime('%I:%M %p PST')
            except:
                call_time = created
        else:
            call_time = 'Unknown'
        
        reason = c.get('endedReason', 'unknown')
        
        # Determine qualification
        qualified_reasons = ['assistant-ended-call', 'silence-timed-out', 'customer-did-not-answer', 'exceeded-max-duration']
        is_qualified = reason in qualified_reasons
        
        # Human-readable outcome
        if reason == 'assistant-ended-call':
            outcome = 'Voicemail'
        elif reason == 'silence-timed-out':
            outcome = 'No Answer'
        elif reason == 'exceeded-max-duration':
            outcome = 'IVR/Long Hold'
        elif reason == 'customer-ended-call':
            outcome = 'Human Answered'
        elif reason == 'customer-did-not-answer':
            outcome = 'No Answer'
        elif 'error' in reason:
            outcome = 'Call Failed'
        else:
            outcome = reason
        
        enriched.append({
            'Business Name': lead.get('name', ''),
            'Phone': phone_raw,
            'Call Time': call_time,
            'City': lead.get('city', ''),
            'State': lead.get('state', ''),
            'Rating': lead.get('rating', ''),
            'Reviews': lead.get('reviews', ''),
            'Website': lead.get('website', ''),
            'Claims 24/7': 'Yes' if lead.get('is_24_hours') == 'True' else 'No',
            'Outcome': outcome,
            'Qualified Lead': 'YES' if is_qualified else 'NO',
            'Sales Pitch': 'Ready to pitch - no overnight coverage!' if is_qualified else 'Has coverage',
        })
    
    # Remove duplicates (keep first call per business)
    seen = set()
    unique = []
    for r in enriched:
        key = r['Phone']
        if key not in seen:
            seen.add(key)
            unique.append(r)
    
    # Sort by qualified first
    unique.sort(key=lambda x: (x['Qualified Lead'] != 'YES', x['Business Name']))
    
    if not unique:
        print("No matching calls found!")
        return
    
    # Save enriched CSV
    csv_path = os.path.join(DATA_DIR, 'overnight_ENRICHED.csv')
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=unique[0].keys())
        writer.writeheader()
        writer.writerows(unique)
    
    # Save TSV for Google Sheets
    tsv_path = os.path.join(DATA_DIR, 'overnight_ENRICHED_SHEETS.tsv')
    with open(tsv_path, 'w') as f:
        f.write('\t'.join(unique[0].keys()) + '\n')
        for r in unique:
            f.write('\t'.join(str(v) for v in r.values()) + '\n')
    
    # Save qualified only
    qualified = [r for r in unique if r['Qualified Lead'] == 'YES']
    qual_path = os.path.join(DATA_DIR, 'overnight_QUALIFIED_SHEETS.tsv')
    with open(qual_path, 'w') as f:
        f.write('\t'.join(qualified[0].keys()) + '\n')
        for r in qualified:
            f.write('\t'.join(str(v) for v in r.values()) + '\n')
    
    print(f"\n{'='*50}")
    print(f"EXPORTED (deduplicated):")
    print(f"  {csv_path}")
    print(f"  - {len(unique)} unique businesses called")
    print(f"  {tsv_path}")
    print(f"  - Ready for Google Sheets import")
    print(f"  {qual_path}")
    print(f"  - {len(qualified)} QUALIFIED leads (no overnight coverage)")
    print(f"{'='*50}")
    
    # Show preview
    print("\nPREVIEW - First 5 qualified leads:")
    print("-" * 100)
    for r in qualified[:5]:
        print(f"  {r['Business Name'][:35]:35} | {r['Phone']:15} | {r['City']:15} | {r['Outcome']}")

if __name__ == '__main__':
    main()


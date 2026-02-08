#!/usr/bin/env python3
"""
Export call results to Google Sheets-ready format.
Outputs a clean TSV that can be pasted directly into Google Sheets.
"""
import csv
import json
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("data")

def get_latest_results():
    """Find the most recent audit results."""
    json_files = sorted(DATA_DIR.glob("audit_*.json"), reverse=True)
    if not json_files:
        print("❌ No audit results found. Run some calls first!")
        return None
    return json_files[0]

def export_for_sheets(json_file: Path = None):
    """Export results in Google Sheets-friendly format."""
    
    if json_file is None:
        json_file = get_latest_results()
        if not json_file:
            return
    
    print(f"📂 Loading: {json_file}")
    
    with open(json_file, 'r') as f:
        results = json.load(f)
    
    # Create TSV for easy paste into Google Sheets
    output_file = DATA_DIR / f"sheets_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tsv"
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter='\t')
        
        # Header row
        writer.writerow([
            'Call Time (PST)',
            'Business Name', 
            'Phone',
            'City',
            'Result',
            'Qualified?',
            'Sales Pitch'
        ])
        
        for r in results:
            analysis = r.get('analysis', {})
            answered_by = analysis.get('answered_by', 'unknown')
            is_qualified = analysis.get('is_qualified', False)
            
            # Generate pitch
            if is_qualified:
                if answered_by in ['voicemail', 'no_answer']:
                    pitch = "Your after-hours calls go to voicemail - you're losing $1500+ emergency jobs to competitors"
                else:
                    pitch = "No live answer after hours - we can fix that"
            else:
                pitch = "Has coverage - lower priority"
            
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %I:%M %p PST"),
                r.get('business_name', ''),
                r.get('phone', ''),
                r.get('location', ''),
                answered_by,
                'YES ✓' if is_qualified else 'NO',
                pitch
            ])
    
    print(f"\n✅ Exported to: {output_file}")
    
    # Count stats
    total = len(results)
    qualified = sum(1 for r in results if r.get('analysis', {}).get('is_qualified'))
    
    print(f"\n📊 SUMMARY:")
    print(f"   Total calls: {total}")
    print(f"   Qualified leads: {qualified} ({qualified/max(total,1)*100:.0f}%)")
    
    print(f"\n📋 TO IMPORT TO GOOGLE SHEETS:")
    print(f"   1. Open Google Sheets")
    print(f"   2. File → Import → Upload")
    print(f"   3. Select: {output_file}")
    print(f"   4. Choose 'Tab' as separator")
    print(f"   5. Done!")
    
    print(f"\n   OR copy this and paste directly:")
    print(f"   cat {output_file} | pbcopy")
    
    return output_file


def print_qualified_leads():
    """Print just the qualified leads for quick copy."""
    json_file = get_latest_results()
    if not json_file:
        return
    
    with open(json_file, 'r') as f:
        results = json.load(f)
    
    qualified = [r for r in results if r.get('analysis', {}).get('is_qualified')]
    
    if not qualified:
        print("No qualified leads yet!")
        return
    
    print("\n🎯 QUALIFIED LEADS (Copy & Paste to Sheets):")
    print("=" * 80)
    print("Business Name\tPhone\tCity\tResult")
    print("-" * 80)
    
    for r in qualified:
        name = r.get('business_name', '')
        phone = r.get('phone', '')
        city = r.get('location', '')
        result = r.get('analysis', {}).get('answered_by', '')
        print(f"{name}\t{phone}\t{city}\t{result}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--qualified":
        print_qualified_leads()
    else:
        export_for_sheets()


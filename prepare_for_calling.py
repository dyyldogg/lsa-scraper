#!/usr/bin/env python3
"""
Convert PersonalInjury CSV to phone list format for calling scripts.
"""
import csv
from pathlib import Path

def convert_csv_to_phone_list(csv_path, output_dir="data"):
    """Convert the PersonalInjury CSV to phone list format."""
    
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    
    phone_list_file = output_dir / "pi_lawyers_phones.txt"
    
    leads = []
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get('name', '').strip()
            phone = row.get('phone', '').strip()
            city = row.get('city', '').strip()
            state = row.get('state', '').strip()
            hours = row.get('hours_summary', '').strip()
            
            if not phone or not name:
                continue
            
            # Format location
            location = f"{city}, {state}" if city and state else ""
            
            # Check if 24/7
            is_24h = "24/7" in hours.upper() or "24 hour" in hours.lower()
            
            # Format: phone<TAB>name<TAB>location<TAB>24/7 flag
            line = f"{phone}\t{name}\t{location}"
            if is_24h:
                line += "\t24/7"
            
            leads.append(line)
    
    # Write phone list file
    with open(phone_list_file, 'w', encoding='utf-8') as f:
        f.write("# Phone list for Vapi caller\n")
        f.write("# Format: phone<TAB>name<TAB>location<TAB>24/7\n")
        f.write("\n".join(leads))
    
    print(f"✅ Converted {len(leads)} leads")
    print(f"📄 Output: {phone_list_file}")
    print(f"\nTo call them:")
    print(f"  python3 vapi_caller.py --file {phone_list_file} --limit 10")
    print(f"  python3 overnight_caller.py  # for autonomous overnight calling")
    
    return phone_list_file

if __name__ == '__main__':
    csv_path = "/Users/dylanrochex/Downloads/PersonalInjury_ALL_20260122_213951 - PersonalInjury_ALL_20260122_213951.csv"
    convert_csv_to_phone_list(csv_path)

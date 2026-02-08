#!/usr/bin/env python3
"""
Simple Twilio Test Caller
Call HVAC leads and detect if they answer or go to voicemail.

Setup:
1. Get Twilio credentials from https://console.twilio.com
2. Buy a phone number (~$1/month)
3. Set environment variables or edit below

Usage:
    python test_caller.py --test                    # Test with 1 call
    python test_caller.py --limit 10                # Call 10 leads
    python test_caller.py --limit 10 --24-only      # Only 24/7 businesses
    python test_caller.py --phone +13105551234      # Call specific number
"""
import os
import csv
import json
import time
import argparse
from datetime import datetime
from pathlib import Path
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

# ═══════════════════════════════════════════════════════════════════════════════
# TWILIO CONFIGURATION - Edit these or set as environment variables
# ═══════════════════════════════════════════════════════════════════════════════

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "YOUR_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "YOUR_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "+1XXXXXXXXXX")  # Your Twilio number

# ═══════════════════════════════════════════════════════════════════════════════

OUTPUT_DIR = Path("data")
OUTPUT_DIR.mkdir(exist_ok=True)

# Results file
RESULTS_FILE = OUTPUT_DIR / f"call_results_{datetime.now().strftime('%Y%m%d')}.csv"


def load_leads(phone_file: str = None) -> list:
    """Load leads from the most recent phone list file."""
    if phone_file:
        file_path = Path(phone_file)
    else:
        # Find the most recent phone list
        phone_files = sorted(OUTPUT_DIR.glob("*_phones.txt"), reverse=True)
        if not phone_files:
            print("❌ No phone list files found in data/")
            return []
        file_path = phone_files[0]
    
    print(f"📂 Loading leads from: {file_path}")
    
    leads = []
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = line.split('\t')
            if len(parts) >= 2:
                leads.append({
                    'phone': parts[0],
                    'name': parts[1],
                    'location': parts[2] if len(parts) > 2 else '',
                    'is_24h': '24/7' in line or '24 hour' in line.lower()
                })
    
    return leads


def make_call(client: Client, to_number: str, from_number: str) -> dict:
    """
    Make a call and detect if human or voicemail answers.
    
    Returns dict with:
        - status: completed, no-answer, busy, failed
        - answered_by: human, machine, unknown
        - duration: seconds
    """
    try:
        # TwiML that plays a brief message
        # This helps detect voicemail vs human
        twiml = '''<Response>
            <Pause length="2"/>
            <Say voice="Polly.Matthew">Hello, this is an automated service verification. Thank you for your time.</Say>
            <Pause length="1"/>
            <Hangup/>
        </Response>'''
        
        call = client.calls.create(
            to=to_number,
            from_=from_number,
            twiml=twiml,
            timeout=30,  # Ring for 30 seconds max
            machine_detection="DetectMessageEnd",  # Detect voicemail
            machine_detection_timeout=10,
        )
        
        print(f"   📞 Call initiated: {call.sid}")
        
        # Poll for completion
        max_wait = 60
        start = time.time()
        
        while time.time() - start < max_wait:
            call = client.calls(call.sid).fetch()
            
            if call.status in ["completed", "failed", "busy", "no-answer", "canceled"]:
                return {
                    'status': call.status,
                    'answered_by': call.answered_by or 'unknown',
                    'duration': int(call.duration) if call.duration else 0,
                    'sid': call.sid
                }
            
            time.sleep(2)
        
        return {'status': 'timeout', 'answered_by': 'unknown', 'duration': 0, 'sid': call.sid}
        
    except TwilioRestException as e:
        print(f"   ❌ Twilio Error: {e.msg}")
        return {'status': 'error', 'answered_by': 'none', 'duration': 0, 'error': str(e.msg)}


def save_result(result: dict):
    """Append result to CSV file."""
    file_exists = RESULTS_FILE.exists()
    
    with open(RESULTS_FILE, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'timestamp', 'phone', 'name', 'location', 'is_24h',
            'status', 'answered_by', 'duration', 'qualified'
        ])
        
        if not file_exists:
            writer.writeheader()
        
        writer.writerow(result)


def run_calls(
    leads: list,
    limit: int = 10,
    only_24h: bool = False,
    delay: int = 5
):
    """Run calls on a list of leads."""
    
    # Validate Twilio credentials
    if TWILIO_ACCOUNT_SID == "YOUR_ACCOUNT_SID":
        print("\n❌ Twilio credentials not configured!")
        print("\nTo set up Twilio:")
        print("1. Go to https://console.twilio.com")
        print("2. Get your Account SID and Auth Token from the dashboard")
        print("3. Buy a phone number (~$1.15/month)")
        print("4. Set environment variables:")
        print("   export TWILIO_ACCOUNT_SID='ACxxxxxx'")
        print("   export TWILIO_AUTH_TOKEN='your_token'")
        print("   export TWILIO_PHONE_NUMBER='+1234567890'")
        return
    
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    
    # Filter leads
    if only_24h:
        leads = [l for l in leads if l.get('is_24h')]
        print(f"📋 Filtered to 24/7 businesses: {len(leads)} leads")
    
    leads = leads[:limit]
    
    print(f"\n{'='*60}")
    print(f"📞 NIGHTLINE AUDIT CALLER")
    print(f"{'='*60}")
    print(f"   Time: {datetime.now().strftime('%I:%M %p %A')}")
    print(f"   Leads to call: {len(leads)}")
    print(f"   From number: {TWILIO_PHONE_NUMBER}")
    print(f"{'='*60}\n")
    
    stats = {'total': 0, 'answered': 0, 'voicemail': 0, 'no_answer': 0, 'failed': 0}
    
    for i, lead in enumerate(leads, 1):
        print(f"\n[{i}/{len(leads)}] {lead['name']}")
        print(f"   Phone: {lead['phone']}")
        print(f"   Location: {lead.get('location', 'N/A')}")
        print(f"   24/7: {'Yes' if lead.get('is_24h') else 'No'}")
        
        # Make the call
        result = make_call(client, lead['phone'], TWILIO_PHONE_NUMBER)
        
        # Determine if qualified (didn't answer)
        qualified = result['status'] in ['no-answer'] or result['answered_by'] in ['machine_start', 'machine_end_beep', 'machine_end_silence', 'machine_end_other']
        
        # Display result
        if result['answered_by'] == 'human':
            print(f"   ✅ ANSWERED by human ({result['duration']}s)")
            stats['answered'] += 1
        elif 'machine' in str(result['answered_by']):
            print(f"   📬 VOICEMAIL detected - QUALIFIED LEAD!")
            stats['voicemail'] += 1
        elif result['status'] == 'no-answer':
            print(f"   ⏰ NO ANSWER - QUALIFIED LEAD!")
            stats['no_answer'] += 1
        elif result['status'] == 'busy':
            print(f"   📵 BUSY")
            stats['failed'] += 1
        else:
            print(f"   ❌ {result['status']}")
            stats['failed'] += 1
        
        stats['total'] += 1
        
        # Save result
        save_result({
            'timestamp': datetime.now().isoformat(),
            'phone': lead['phone'],
            'name': lead['name'],
            'location': lead.get('location', ''),
            'is_24h': lead.get('is_24h', False),
            'status': result['status'],
            'answered_by': result['answered_by'],
            'duration': result['duration'],
            'qualified': qualified
        })
        
        # Delay between calls
        if i < len(leads):
            print(f"   ⏳ Waiting {delay}s before next call...")
            time.sleep(delay)
    
    # Summary
    qualified_count = stats['voicemail'] + stats['no_answer']
    
    print(f"\n{'='*60}")
    print(f"📊 RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"   Total calls: {stats['total']}")
    print(f"   Answered (human): {stats['answered']}")
    print(f"   Voicemail: {stats['voicemail']}")
    print(f"   No Answer: {stats['no_answer']}")
    print(f"   Failed/Busy: {stats['failed']}")
    print(f"{'='*60}")
    print(f"   🎯 QUALIFIED LEADS: {qualified_count} ({qualified_count/max(stats['total'],1)*100:.0f}%)")
    print(f"{'='*60}")
    print(f"\n💾 Results saved to: {RESULTS_FILE}")
    
    if qualified_count > 0:
        print(f"\n💰 You have {qualified_count} leads who DIDN'T ANSWER!")
        print("   Use this for your sales pitch tomorrow:")
        print('   "I called your 24/7 line last night and it went to voicemail."')


def test_single_call(phone: str):
    """Test a single call to a specific number."""
    if TWILIO_ACCOUNT_SID == "YOUR_ACCOUNT_SID":
        print("\n❌ Twilio credentials not configured!")
        return
    
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    
    print(f"\n📞 Test calling: {phone}")
    print(f"   From: {TWILIO_PHONE_NUMBER}")
    
    result = make_call(client, phone, TWILIO_PHONE_NUMBER)
    
    print(f"\n📊 Result:")
    print(f"   Status: {result['status']}")
    print(f"   Answered by: {result['answered_by']}")
    print(f"   Duration: {result['duration']}s")


def main():
    parser = argparse.ArgumentParser(description="Twilio Test Caller for HVAC Leads")
    parser.add_argument("--test", action="store_true", help="Test mode - call 1 lead")
    parser.add_argument("--phone", type=str, help="Call a specific phone number")
    parser.add_argument("--limit", type=int, default=10, help="Max calls to make")
    parser.add_argument("--24-only", action="store_true", dest="only_24h", help="Only call 24/7 businesses")
    parser.add_argument("--delay", type=int, default=5, help="Seconds between calls")
    parser.add_argument("--file", type=str, help="Phone list file to use")
    
    args = parser.parse_args()
    
    if args.phone:
        test_single_call(args.phone)
    else:
        leads = load_leads(args.file)
        if not leads:
            return
        
        print(f"📋 Loaded {len(leads)} leads")
        
        limit = 1 if args.test else args.limit
        run_calls(leads, limit=limit, only_24h=args.only_24h, delay=args.delay)


if __name__ == "__main__":
    main()


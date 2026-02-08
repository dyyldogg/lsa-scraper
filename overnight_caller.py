#!/usr/bin/env python3
"""
OVERNIGHT AUTONOMOUS CALLER
- Runs all calls without supervision
- Saves progress every 10 calls (won't lose progress if it crashes)
- Creates final Google Sheets-ready export when done
- Run with: nohup python3 overnight_caller.py > overnight.log 2>&1 &
"""
import os
import csv
import json
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════
VAPI_API_KEY = os.environ.get("VAPI_API_KEY", "d6dc0c9c-3cc7-40f7-a67f-16daea564e84")
VAPI_BASE_URL = "https://api.vapi.ai"
VAPI_PHONE_ID = "ea6c590f-5bd7-4eed-9113-dbfda934816a"  # Twilio number
ASSISTANT_ID = "bd931f9a-77bd-4d4e-9e59-e003ed78a3f0"   # Stealth assistant

OUTPUT_DIR = Path("data")
PST = timezone(timedelta(hours=-8))

# How many calls before saving progress
SAVE_EVERY = 10
DELAY_BETWEEN_CALLS = 3  # seconds
MAX_CALLS = 100  # Set to 985 for all leads

# ═══════════════════════════════════════════════════════════════════════════════
# LOAD LEADS
# ═══════════════════════════════════════════════════════════════════════════════
def load_leads():
    """Load leads from phone list."""
    files = sorted(OUTPUT_DIR.glob("*_phones.txt"), reverse=True)
    if not files:
        return []
    
    leads = []
    with open(files[0], 'r') as f:
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
                    'is_24h': '24/7' in line
                })
    return leads

# ═══════════════════════════════════════════════════════════════════════════════
# MAKE CALL
# ═══════════════════════════════════════════════════════════════════════════════
def make_call(phone: str, business_name: str) -> dict:
    """Make a single call and wait for result."""
    headers = {
        "Authorization": f"Bearer {VAPI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "assistantId": ASSISTANT_ID,
        "phoneNumberId": VAPI_PHONE_ID,
        "customer": {"number": phone},
        "metadata": {
            "business_name": business_name,
            "timestamp": datetime.now().isoformat()
        }
    }
    
    # Start call
    resp = requests.post(f"{VAPI_BASE_URL}/call/phone", headers=headers, json=payload)
    
    if resp.status_code not in [200, 201]:
        return {"status": "error", "error": resp.text, "phone": phone, "business_name": business_name}
    
    call_id = resp.json().get("id")
    print(f"   📞 Call started: {call_id[:8]}...")
    
    # Wait for call to complete (max 90 seconds)
    for _ in range(30):
        time.sleep(3)
        resp = requests.get(f"{VAPI_BASE_URL}/call/{call_id}", headers=headers)
        if resp.status_code == 200:
            call = resp.json()
            if call.get("status") in ["ended", "failed"]:
                return analyze_call(call, phone, business_name)
    
    return {"status": "timeout", "phone": phone, "business_name": business_name}

def analyze_call(call: dict, phone: str, business_name: str) -> dict:
    """Analyze call result."""
    end_reason = call.get("endedReason", "unknown")
    transcript = ""
    for msg in call.get("messages", []):
        content = msg.get("content", "") or msg.get("message", "")
        if content:
            transcript += f"{msg.get('role', '')}: {content}\n"
    
    # Classify result
    transcript_lower = transcript.lower()
    
    if end_reason == "customer-did-not-answer":
        result = "no_answer"
        qualified = True
    elif end_reason in ["silence-timed-out", "exceeded-max-duration"]:
        if "leave" in transcript_lower or "message" in transcript_lower or "beep" in transcript_lower:
            result = "voicemail"
            qualified = True
        else:
            result = "voicemail_likely"
            qualified = True
    elif "answering service" in transcript_lower or "how can i help" in transcript_lower or "callback" in transcript_lower:
        result = "answering_service"
        qualified = False
    elif "wrong number" in transcript_lower or "sorry" in transcript_lower:
        result = "human_answered"
        qualified = False
    elif "leave" in transcript_lower or "message" in transcript_lower:
        result = "voicemail"
        qualified = True
    else:
        result = "unknown"
        qualified = False
    
    return {
        "status": "completed",
        "phone": phone,
        "business_name": business_name,
        "result": result,
        "qualified": qualified,
        "end_reason": end_reason,
        "duration": call.get("duration", 0),
        "transcript": transcript[:500]
    }

# ═══════════════════════════════════════════════════════════════════════════════
# SAVE RESULTS
# ═══════════════════════════════════════════════════════════════════════════════
def save_progress(results: list, final: bool = False):
    """Save current results to files."""
    if not results:
        return
    
    timestamp = datetime.now(PST).strftime("%Y%m%d_%H%M%S")
    prefix = f"overnight_{'FINAL' if final else 'progress'}_{timestamp}"
    
    # JSON
    with open(OUTPUT_DIR / f"{prefix}.json", 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    # Google Sheets TSV
    tsv_file = OUTPUT_DIR / f"{prefix}_SHEETS.tsv"
    with open(tsv_file, 'w', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['Business', 'Phone', 'City', 'Result', 'Qualified', 'Sales Pitch'])
        
        for r in results:
            qualified = r.get('qualified', False)
            result = r.get('result', 'unknown')
            
            if qualified:
                pitch = "After-hours calls go to voicemail - losing $1500+ emergency jobs"
            else:
                pitch = "Has coverage"
            
            writer.writerow([
                r.get('business_name', ''),
                r.get('phone', ''),
                r.get('location', ''),
                result,
                'YES ✓' if qualified else 'NO',
                pitch
            ])
    
    # Qualified leads only
    qualified_leads = [r for r in results if r.get('qualified')]
    if qualified_leads:
        qual_file = OUTPUT_DIR / f"{prefix}_QUALIFIED.tsv"
        with open(qual_file, 'w', newline='') as f:
            writer = csv.writer(f, delimiter='\t')
            writer.writerow(['Business', 'Phone', 'City', 'Result'])
            for r in qualified_leads:
                writer.writerow([
                    r.get('business_name', ''),
                    r.get('phone', ''),
                    r.get('location', ''),
                    r.get('result', '')
                ])
    
    total = len(results)
    qual_count = len(qualified_leads)
    print(f"\n💾 Saved: {total} calls, {qual_count} qualified ({qual_count/max(total,1)*100:.0f}%)")
    print(f"   📄 {tsv_file}")

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("🌙 OVERNIGHT AUTONOMOUS CALLER")
    print("=" * 60)
    print(f"   Started: {datetime.now(PST).strftime('%Y-%m-%d %I:%M %p PST')}")
    print(f"   Max calls: {MAX_CALLS}")
    print(f"   Save every: {SAVE_EVERY} calls")
    print("=" * 60)
    
    leads = load_leads()
    if not leads:
        print("❌ No leads found!")
        return
    
    print(f"📋 Loaded {len(leads)} leads")
    leads = leads[:MAX_CALLS]
    
    results = []
    
    for i, lead in enumerate(leads, 1):
        print(f"\n[{i}/{len(leads)}] 📞 {lead['name']}")
        print(f"   Phone: {lead['phone']}")
        
        result = make_call(lead['phone'], lead['name'])
        result['location'] = lead.get('location', '')
        results.append(result)
        
        # Show result
        if result.get('qualified'):
            print(f"   ✅ QUALIFIED - {result.get('result')}")
        else:
            print(f"   ❌ {result.get('result')}")
        
        # Save progress periodically
        if i % SAVE_EVERY == 0:
            save_progress(results)
        
        # Delay before next call
        if i < len(leads):
            time.sleep(DELAY_BETWEEN_CALLS)
    
    # Final save
    print("\n" + "=" * 60)
    print("🎉 ALL CALLS COMPLETE!")
    print("=" * 60)
    save_progress(results, final=True)
    
    # Summary
    total = len(results)
    qualified = sum(1 for r in results if r.get('qualified'))
    print(f"\n📊 FINAL RESULTS:")
    print(f"   Total calls: {total}")
    print(f"   Qualified leads: {qualified} ({qualified/max(total,1)*100:.0f}%)")
    print(f"\n🎯 Ready to import to Google Sheets!")
    print(f"   Look for: data/overnight_FINAL_*_SHEETS.tsv")

if __name__ == "__main__":
    main()


#!/usr/bin/env python3
"""
Vapi.ai Smart Caller for HVAC Lead Auditing
- Calls businesses
- Navigates IVR menus automatically
- Transcribes everything
- AI determines: Human / Voicemail / Answering Service
- Logs results for sales outreach

Usage:
    python vapi_caller.py --test                  # Test with 1 call
    python vapi_caller.py --limit 10              # Call 10 leads
    python vapi_caller.py --limit 50 --24-only    # Call 50 24/7 businesses
"""
import os
import csv
import json
import time
import argparse
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, List

# PST timezone (UTC-8)
PST = timezone(timedelta(hours=-8))

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

from dotenv import load_dotenv
load_dotenv()

VAPI_API_KEY = os.environ.get("VAPI_API_KEY", "")
VAPI_BASE_URL = "https://api.vapi.ai"

# Your Vapi phone number ID
# Get it from: Vapi Dashboard > Phone Numbers > click your number > copy the ID
VAPI_PHONE_ID = os.environ.get("VAPI_PHONE_ID", "")

OUTPUT_DIR = Path("data")
OUTPUT_DIR.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════════
# VAPI ASSISTANT CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# CHEAPEST POSSIBLE AGENT CONFIG
# ═══════════════════════════════════════════════════════════════════════════════
# Cost breakdown per minute:
#   - LLM: GPT-3.5-turbo = $0.002/min (vs GPT-4o = $0.05/min) 
#   - Voice: Deepgram = $0.007/min (vs ElevenLabs = $0.30/min)
#   - Transcriber: Deepgram Nova = $0.0043/min
#   - Vapi platform: $0.05/min
#   - Twilio: ~$0.014/min
# TOTAL: ~$0.08/min (vs $0.45/min with premium options)
# ═══════════════════════════════════════════════════════════════════════════════

ASSISTANT_CONFIG = {
    "name": "Stealth",
    "model": {
        "provider": "openai",
        "model": "gpt-3.5-turbo",  # CHEAPEST LLM - 25x cheaper than GPT-4o
        "messages": [
            {
                "role": "system", 
                "content": """Silent listener. Rules:
1. STAY SILENT until human speaks
2. IVR menu: press key for emergency/service/operator. If unsure press 0
3. Voicemail ("leave message"/"beep"): hang up with endCall
4. Human answers: say "Sorry wrong number!" then endCall
5. Never explain why calling"""
            }
        ],
        "temperature": 0.1,
        "maxTokens": 50  # Limit response length = less cost
    },
    "voice": {
        "provider": "deepgram",  # CHEAPEST voice - 40x cheaper than ElevenLabs
        "voiceId": "asteria"  # Valid Deepgram voice ID
    },
    "firstMessage": "",
    "firstMessageMode": "assistant-waits-for-user",
    "dialKeypadFunctionEnabled": True,
    "endCallFunctionEnabled": True,
    "silenceTimeoutSeconds": 15,  # Shorter = less cost
    "maxDurationSeconds": 60,  # Max 1 min per call
    "transcriber": {
        "provider": "deepgram",  # Cheapest transcriber
        "model": "nova-2",
        "language": "en"
    },
    "recordingEnabled": False  # Disable recording = saves storage cost
}


class VapiCaller:
    """Vapi.ai integration for smart audit calls."""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or VAPI_API_KEY
        if not self.api_key:
            raise ValueError("VAPI_API_KEY not set. Copy env.example to .env and fill in your key.")
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.assistant_id = None
    
    def create_assistant(self, force_new: bool = False) -> str:
        """Create or get the audit assistant."""
        # Check for existing assistants
        response = requests.get(
            f"{VAPI_BASE_URL}/assistant",
            headers=self.headers
        )
        
        if response.status_code == 200 and not force_new:
            assistants = response.json()
            for asst in assistants:
                if asst.get("name") == "Stealth":
                    print(f"   Using existing assistant: {asst['id']}")
                    self.assistant_id = asst["id"]
                    return asst["id"]
        
        # Delete ALL old assistants if forcing new
        if force_new and response.status_code == 200:
            assistants = response.json()
            for asst in assistants:
                requests.delete(
                    f"{VAPI_BASE_URL}/assistant/{asst['id']}",
                    headers=self.headers
                )
                print(f"   Deleted old assistant: {asst['id']}")
        
        # Create new assistant with updated config
        response = requests.post(
            f"{VAPI_BASE_URL}/assistant",
            headers=self.headers,
            json=ASSISTANT_CONFIG
        )
        
        if response.status_code in [200, 201]:
            data = response.json()
            self.assistant_id = data["id"]
            print(f"   Created NEW assistant with IVR support: {self.assistant_id}")
            return self.assistant_id
        else:
            raise Exception(f"Failed to create assistant: {response.text}")
    
    def make_call(self, phone_number: str, business_name: str = "") -> Dict:
        """
        Make an audit call to a phone number.
        
        Returns:
            Dict with call results including transcript and AI analysis
        """
        if not self.assistant_id:
            self.create_assistant()
        
        # Prepare call payload
        payload = {
            "assistantId": self.assistant_id,
            "customer": {
                "number": phone_number
            },
            "metadata": {
                "business_name": business_name,
                "call_type": "audit",
                "timestamp": datetime.now().isoformat()
            }
        }
        
        # Add phone number ID (required for outbound calls)
        payload["phoneNumberId"] = VAPI_PHONE_ID
        
        # Initiate call
        response = requests.post(
            f"{VAPI_BASE_URL}/call/phone",
            headers=self.headers,
            json=payload
        )
        
        if response.status_code not in [200, 201]:
            return {
                "status": "error",
                "error": response.text,
                "phone": phone_number
            }
        
        call_data = response.json()
        call_id = call_data.get("id")
        
        print(f"   📞 Call initiated: {call_id}")
        
        # Poll for completion
        result = self._wait_for_completion(call_id)
        result["phone"] = phone_number
        result["business_name"] = business_name
        
        return result
    
    def _wait_for_completion(self, call_id: str, timeout: int = 180) -> Dict:
        """Wait for call to complete and get results."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            response = requests.get(
                f"{VAPI_BASE_URL}/call/{call_id}",
                headers=self.headers
            )
            
            if response.status_code != 200:
                time.sleep(2)
                continue
            
            call = response.json()
            status = call.get("status")
            
            if status in ["ended", "failed"]:
                return self._analyze_call(call)
            
            time.sleep(3)
        
        return {"status": "timeout", "call_id": call_id}
    
    def _analyze_call(self, call: Dict) -> Dict:
        """Analyze completed call and determine outcome."""
        
        # Get transcript
        transcript = call.get("transcript", "")
        messages = call.get("messages", [])
        duration = call.get("duration", 0)
        recording_url = call.get("recordingUrl", "")
        end_reason = call.get("endedReason", "unknown")
        
        # Build full transcript text
        transcript_text = ""
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "") or msg.get("message", "")
            if content:
                transcript_text += f"{role}: {content}\n"
        
        # AI Analysis - determine what answered
        analysis = self._classify_response(transcript_text, end_reason, duration)
        
        return {
            "status": "completed",
            "call_id": call.get("id"),
            "duration_seconds": duration,
            "transcript": transcript_text,
            "recording_url": recording_url,
            "end_reason": end_reason,
            "analysis": analysis
        }
    
    def _classify_response(self, transcript: str, end_reason: str, duration: int) -> Dict:
        """Classify what answered the call based on transcript and end reason."""
        
        transcript_lower = transcript.lower() if transcript else ""
        
        # Classification logic
        answered_by = "unknown"
        is_qualified = False
        confidence = "medium"
        notes = ""
        
        # FIRST: Check end_reason - this is most reliable
        if end_reason == "customer-did-not-answer":
            return {
                "answered_by": "no_answer",
                "is_qualified": True,
                "confidence": "high",
                "notes": "NO ANSWER - QUALIFIED LEAD! 🎯"
            }
        
        if end_reason == "customer-busy":
            return {
                "answered_by": "busy",
                "is_qualified": False,
                "confidence": "high",
                "notes": "Line busy - retry later"
            }
        
        if end_reason in ["silence-timed-out", "assistant-did-not-speak"]:
            # Check if there was any human speech in transcript
            if not transcript_lower or len(transcript_lower.strip()) < 50:
                return {
                    "answered_by": "voicemail_or_no_answer",
                    "is_qualified": True,
                    "confidence": "high",
                    "notes": "Silence/Voicemail - QUALIFIED LEAD! 🎯"
                }
        
        # Check for voicemail indicators
        voicemail_indicators = [
            "leave a message", "leave your message", "after the tone",
            "after the beep", "not available", "can't come to the phone",
            "voicemail", "mailbox", "record your message", "please leave",
            "at the tone", "currently unavailable"
        ]
        
        # Check for answering service indicators  
        service_indicators = [
            "how may i help", "how can i help", "what is your emergency",
            "can i get your name", "may i have your", "what's the address",
            "answering service", "after hours service", "on-call",
            "let me dispatch", "i'll page", "callback number",
            "this call may be recorded", "may be monitored"
        ]
        
        # Check for IVR indicators
        ivr_indicators = [
            "press 1", "press 2", "press one", "press two",
            "dial 0", "for sales", "for service", "for emergencies",
            "main menu", "please select", "extension"
        ]
        
        # Check for human conversation indicators
        human_indicators = [
            "wrong number", "no problem", "have a good", "you too",
            "can i help you", "what do you need", "who is this",
            "hello", "hi there", "good evening"
        ]
        
        # Analyze transcript
        has_voicemail = any(ind in transcript_lower for ind in voicemail_indicators)
        has_service = any(ind in transcript_lower for ind in service_indicators)
        has_ivr = any(ind in transcript_lower for ind in ivr_indicators)
        has_human = any(ind in transcript_lower for ind in human_indicators)
        
        # Determine classification based on transcript content
        if has_service:
            answered_by = "answering_service"
            is_qualified = False
            confidence = "high"
            notes = "Answering service detected - they have after-hours coverage"
        elif has_voicemail:
            answered_by = "voicemail"
            is_qualified = True
            confidence = "high"
            notes = "Voicemail detected - QUALIFIED LEAD! 🎯"
        elif has_human and not has_ivr:
            answered_by = "human"
            is_qualified = False
            confidence = "high"
            notes = "Human answered the call"
        elif has_ivr and not has_human and not has_service:
            answered_by = "ivr_only"
            is_qualified = True
            confidence = "medium"
            notes = "IVR menu but no human - likely QUALIFIED"
        elif duration and duration < 10:
            answered_by = "no_answer"
            is_qualified = True
            confidence = "high"
            notes = "Call too short - QUALIFIED LEAD! 🎯"
        else:
            answered_by = "unknown"
            is_qualified = False
            confidence = "low"
            notes = "Could not determine - manual review needed"
        
        return {
            "answered_by": answered_by,
            "is_qualified": is_qualified,
            "confidence": confidence,
            "notes": notes
        }


# Also add helper to show nice summary


def load_leads(file_path: str = None) -> List[Dict]:
    """Load leads from phone list file."""
    if file_path:
        fp = Path(file_path)
    else:
        # Find most recent
        files = sorted(OUTPUT_DIR.glob("*_phones.txt"), reverse=True)
        if not files:
            return []
        fp = files[0]
    
    print(f"📂 Loading leads from: {fp}")
    
    leads = []
    with open(fp, 'r') as f:
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


def save_results(results: List[Dict], filename: str = None):
    """Save call results to CSV and JSON with PST timestamps."""
    if not results:
        return
    
    now_pst = datetime.now(PST)
    timestamp = now_pst.strftime("%Y%m%d_%H%M%S")
    prefix = filename or f"audit_{timestamp}"
    
    # ═══════════════════════════════════════════════════════════════════════════
    # MAIN CSV - All calls with full details
    # ═══════════════════════════════════════════════════════════════════════════
    csv_file = OUTPUT_DIR / f"{prefix}.csv"
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'call_time_pst',      # When call was made (PST)
            'business_name',       # Company name
            'phone',               # Phone number
            'location',            # City, State
            'claims_24_7',         # Do they advertise 24/7?
            'result',              # voicemail/human/no_answer/answering_service
            'qualified_lead',      # TRUE = no one answered = potential sale
            'duration_sec',        # Call length
            'notes'                # AI analysis
        ])
        
        for r in results:
            analysis = r.get('analysis', {})
            writer.writerow([
                now_pst.strftime("%Y-%m-%d %I:%M %p PST"),
                r.get('business_name', ''),
                r.get('phone', ''),
                r.get('location', ''),
                'YES' if r.get('is_24h') else 'NO',
                analysis.get('answered_by', 'unknown'),
                'TRUE' if analysis.get('is_qualified') else 'FALSE',
                r.get('duration_seconds', ''),
                analysis.get('notes', '')
            ])
    
    # JSON (full data for debugging)
    json_file = OUTPUT_DIR / f"{prefix}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, default=str)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # QUALIFIED LEADS - Hot prospects ready to sell to!
    # ═══════════════════════════════════════════════════════════════════════════
    qualified = [r for r in results if r.get('analysis', {}).get('is_qualified')]
    if qualified:
        qual_file = OUTPUT_DIR / f"{prefix}_QUALIFIED.csv"
        with open(qual_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'call_time_pst', 'business_name', 'phone', 'location', 
                'claims_24_7', 'what_happened', 'sales_pitch'
            ])
            for r in qualified:
                analysis = r.get('analysis', {})
                claims_24 = r.get('is_24h', False)
                what = analysis.get('answered_by', 'unknown')
                
                # Generate sales pitch based on findings
                if claims_24 and what in ['voicemail', 'no_answer']:
                    pitch = "You claim 24/7 but we called and got voicemail - you're losing emergency jobs!"
                elif what == 'voicemail':
                    pitch = "Your after-hours calls go to voicemail - potential customers are calling competitors"
                else:
                    pitch = "No live answer after hours - we can fix that"
                
                writer.writerow([
                    now_pst.strftime("%Y-%m-%d %I:%M %p PST"),
                    r.get('business_name', ''),
                    r.get('phone', ''),
                    r.get('location', ''),
                    'YES' if claims_24 else 'NO',
                    what,
                    pitch
                ])
        print(f"   🎯 QUALIFIED: {qual_file}")
    
    print(f"   📄 All results: {csv_file}")
    print(f"   📄 Raw data: {json_file}")


def run_audit(
    leads: List[Dict],
    limit: int = 10,
    only_24h: bool = False,
    delay: int = 5,
    force_new_ai: bool = False
):
    """Run the audit calls."""
    
    if not VAPI_API_KEY:
        print("\n❌ VAPI_API_KEY not set!")
        print("\nSetup:")
        print("1. Copy env.example to .env")
        print("2. Go to https://vapi.ai and sign up")
        print("3. Get your API key from the dashboard")
        print("4. Add it to .env: VAPI_API_KEY=your_key_here")
        return
    
    if not VAPI_PHONE_ID:
        print("\n❌ VAPI_PHONE_ID not set!")
        print("\nSetup:")
        print("1. Go to Vapi Dashboard > Phone Numbers")
        print("2. Import your Twilio number (or buy one)")
        print("3. Click the number and copy the ID")
        print("4. Add it to .env: VAPI_PHONE_ID=your_phone_id_here")
        return
    
    caller = VapiCaller()
    
    # Create assistant first
    print("\n🤖 Setting up AI assistant...")
    caller.create_assistant(force_new=force_new_ai)
    
    # Filter leads
    if only_24h:
        leads = [l for l in leads if l.get('is_24h')]
    
    leads = leads[:limit]
    
    print(f"\n{'='*60}")
    print(f"📞 NIGHTLINE AI AUDIT CALLER")
    print(f"{'='*60}")
    print(f"   Time: {datetime.now().strftime('%I:%M %p %A')}")
    print(f"   Leads to call: {len(leads)}")
    print(f"   AI: GPT-4o + Voice")
    print(f"{'='*60}\n")
    
    results = []
    stats = {'total': 0, 'qualified': 0, 'answered': 0, 'service': 0, 'failed': 0}
    
    for i, lead in enumerate(leads, 1):
        print(f"\n[{i}/{len(leads)}] 📞 {lead['name']}")
        print(f"   Phone: {lead['phone']}")
        print(f"   Location: {lead.get('location', 'N/A')}")
        
        result = caller.make_call(lead['phone'], lead['name'])
        result['location'] = lead.get('location', '')
        result['is_24h'] = lead.get('is_24h', False)
        results.append(result)
        
        # Show result
        analysis = result.get('analysis', {})
        answered_by = analysis.get('answered_by', 'unknown')
        is_qualified = analysis.get('is_qualified', False)
        
        stats['total'] += 1
        
        if is_qualified:
            print(f"   ✅ QUALIFIED - {analysis.get('notes', '')}")
            stats['qualified'] += 1
        elif answered_by == 'human':
            print(f"   👤 Human answered")
            stats['answered'] += 1
        elif answered_by == 'answering_service':
            print(f"   🏢 Answering service")
            stats['service'] += 1
        else:
            print(f"   ❓ {answered_by}")
            stats['failed'] += 1
        
        # Delay between calls
        if i < len(leads):
            print(f"   ⏳ Waiting {delay}s...")
            time.sleep(delay)
    
    # Save results
    print(f"\n💾 Saving results...")
    save_results(results)
    
    # Summary
    print(f"\n{'='*60}")
    print(f"📊 AUDIT COMPLETE")
    print(f"{'='*60}")
    print(f"   Total calls: {stats['total']}")
    print(f"   Human answered: {stats['answered']}")
    print(f"   Answering service: {stats['service']}")
    print(f"   Failed/Unknown: {stats['failed']}")
    print(f"{'='*60}")
    print(f"   🎯 QUALIFIED LEADS: {stats['qualified']} ({stats['qualified']/max(stats['total'],1)*100:.0f}%)")
    print(f"{'='*60}")
    
    if stats['qualified'] > 0:
        print(f"\n💰 {stats['qualified']} businesses didn't answer properly!")
        print("   These are your hot leads for tomorrow's sales calls.")


def main():
    parser = argparse.ArgumentParser(description="Vapi AI Audit Caller")
    parser.add_argument("--test", action="store_true", help="Test with 1 call")
    parser.add_argument("--phone", type=str, help="Call specific number")
    parser.add_argument("--limit", type=int, default=10, help="Max calls")
    parser.add_argument("--24-only", dest="only_24h", action="store_true", help="Only 24/7 businesses")
    parser.add_argument("--delay", type=int, default=5, help="Seconds between calls")
    parser.add_argument("--file", type=str, help="Phone list file")
    parser.add_argument("--new-ai", dest="new_ai", action="store_true", help="Create fresh AI assistant")
    
    args = parser.parse_args()
    
    if args.phone:
        # Single test call
        caller = VapiCaller()
        caller.create_assistant()
        result = caller.make_call(args.phone, "Test Call")
        print(json.dumps(result, indent=2, default=str))
    else:
        leads = load_leads(args.file)
        if not leads:
            print("❌ No leads found")
            return
        
        print(f"📋 Loaded {len(leads)} leads")
        
        limit = 1 if args.test else args.limit
        run_audit(leads, limit=limit, only_24h=args.only_24h, delay=args.delay, force_new_ai=args.new_ai)


if __name__ == "__main__":
    main()


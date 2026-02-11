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
                "content": """You are a COMPLETELY SILENT call observer. ABSOLUTE rules:
1. NEVER speak. Do not say a single word. Stay 100% silent the entire call.
2. IVR menu: press the key for service/emergency/operator/receptionist. If unsure press 0.
3. STAY ON THE LINE through everything: hold music, disclaimers like "this call may be recorded", "please hold", ringing, silence - WAIT through all of it. Do NOT hang up.
4. Only use endCall if you hear a CLEAR voicemail beep/tone asking you to leave a message (the actual beep, not just a greeting).
5. If a real human answers and speaks to you directly (asks who you are, how they can help), stay silent for 3 seconds then endCall.
6. You NEVER speak. No greetings, no apologies, no words at all. Total silence."""
            }
        ],
        "temperature": 0.1,
        "maxTokens": 50  # Minimum allowed by Vapi
    },
    "voice": {
        "provider": "deepgram",  # CHEAPEST voice
        "voiceId": "asteria"
    },
    "firstMessage": "",
    "firstMessageMode": "assistant-waits-for-user",
    "dialKeypadFunctionEnabled": True,
    "endCallFunctionEnabled": True,
    "silenceTimeoutSeconds": 25,  # Wait through disclaimers/hold but don't waste time on dead air
    "maxDurationSeconds": 120,  # 2 min max - enough to get through IVR + hold to a person
    "transcriber": {
        "provider": "deepgram",  # Cheapest transcriber
        "model": "nova-2",
        "language": "en"
    },
    "recordingEnabled": False
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
            print(f"   Deleting {len(assistants)} old assistants...")
            for i, asst in enumerate(assistants):
                resp_del = requests.delete(
                    f"{VAPI_BASE_URL}/assistant/{asst['id']}",
                    headers=self.headers
                )
                if resp_del.status_code == 429:
                    print(f"   Rate limited, waiting 5s...")
                    time.sleep(5)
                    requests.delete(f"{VAPI_BASE_URL}/assistant/{asst['id']}", headers=self.headers)
                if i % 5 == 4:
                    time.sleep(1)  # Brief pause every 5 deletes
            print(f"   Deleted all old assistants")
        
        # Create new assistant with updated config (with retry for rate limits)
        for attempt in range(3):
            response = requests.post(
                f"{VAPI_BASE_URL}/assistant",
                headers=self.headers,
                json=ASSISTANT_CONFIG
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                self.assistant_id = data["id"]
                print(f"   Created NEW assistant: {self.assistant_id}")
                return self.assistant_id
            elif response.status_code == 429:
                wait = 10 * (attempt + 1)
                print(f"   Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise Exception(f"Failed to create assistant: {response.text}")
        
        raise Exception("Failed to create assistant after 3 attempts (rate limited)")
    
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
    
    def _wait_for_completion(self, call_id: str, timeout: int = 150) -> Dict:
        """Wait for call to complete and get results."""
        start_time = time.time()
        poll_interval = 2  # Start fast
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(
                    f"{VAPI_BASE_URL}/call/{call_id}",
                    headers=self.headers,
                    timeout=10
                )
                
                if response.status_code != 200:
                    time.sleep(2)
                    continue
                
                # Guard against empty responses
                if not response.text or not response.text.strip():
                    time.sleep(2)
                    continue
                
                call = response.json()
                status = call.get("status")
                
                if status in ["ended", "failed"]:
                    return self._analyze_call(call)
                
            except (requests.exceptions.JSONDecodeError, requests.exceptions.ConnectionError, 
                    requests.exceptions.Timeout, Exception) as e:
                print(f"      ⚠️ Poll error: {e}, retrying...")
                time.sleep(3)
                continue
            
            time.sleep(poll_interval)
            # After 30s, slow down polling slightly
            if time.time() - start_time > 30:
                poll_interval = 3
        
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
        
        # Build a human-readable summary of what happened
        summary_parts = []
        summary_parts.append(f"Duration: {duration}s")
        summary_parts.append(f"End reason: {end_reason}")
        
        if not transcript_text.strip():
            summary_parts.append("Nobody spoke / silence the whole time")
        else:
            # Count how many different speakers
            lines = [l for l in transcript_text.strip().split('\n') if l.strip()]
            summary_parts.append(f"Transcript lines: {len(lines)}")
        
        if "press" in transcript_text.lower() or "menu" in transcript_text.lower():
            summary_parts.append("Had IVR/phone menu")
        if "leave" in transcript_text.lower() and "message" in transcript_text.lower():
            summary_parts.append("Hit voicemail prompt")
        if "answering service" in transcript_text.lower() or "how can i help" in transcript_text.lower():
            summary_parts.append("Answering service picked up")
            
        analysis["summary"] = " | ".join(summary_parts)
        
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
        """Classify what answered the call using Grok 4 Fast reasoning."""
        
        # FIRST: Check end_reason for obvious cases
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
        
        # Strip out the system prompt from transcript before analyzing
        user_transcript = ""
        if transcript:
            lines = transcript.strip().split('\n')
            user_lines = [l for l in lines if not l.startswith("system:")]
            user_transcript = '\n'.join(user_lines).strip()
        
        # If no meaningful transcript, it's silence/no answer
        if not user_transcript or len(user_transcript) < 10:
            return {
                "answered_by": "no_answer",
                "is_qualified": True,
                "confidence": "high",
                "notes": "Silence/No answer - QUALIFIED LEAD! 🎯"
            }
        
        # Use Grok 4 Fast to classify
        try:
            return self._grok_classify(user_transcript, end_reason, duration)
        except Exception as e:
            print(f"      ⚠️ Grok classification failed: {e}, using fallback")
            return self._fallback_classify(user_transcript, end_reason, duration)
    
    def _grok_classify(self, transcript: str, end_reason: str, duration: int) -> Dict:
        """Use Grok 4 Fast reasoning to classify the call."""
        import os
        
        xai_key = os.environ.get("XAI_API_KEY", "")
        if not xai_key:
            raise ValueError("XAI_API_KEY not set")
        
        prompt = f"""You are analyzing phone call transcripts. We called a personal injury law firm after hours using a SILENT AI caller that never speaks. Our goal is to audit whether a REAL LIVE PERSON eventually answers.

IMPORTANT TRANSCRIPT FORMAT:
- "bot:" lines = OUR silent AI caller (always empty/silent, ignore these)
- "user:" lines = THE OTHER SIDE (the law firm's phone system or whoever picked up)

TRANSCRIPT:
{transcript}

CALL END REASON: {end_reason}
CALL DURATION: {duration} seconds

CRITICAL RULE ABOUT "THIS CALL MAY BE RECORDED":
Phrases like "this call may be recorded", "this call is recorded", "this call will be recorded for quality purposes", "this call may be monitored" are just standard PRE-CALL DISCLAIMERS. They are automated messages that play BEFORE you get connected to anyone. By themselves they do NOT prove an answering service or live person answered. They are just legal disclaimers. Ignore them for classification purposes.

Classify what answered the phone into exactly ONE category:

1. voicemail - A RECORDED greeting followed by a beep/tone to leave a message. Key signs: "leave a message after the beep/tone", "please leave your name and number", "not available right now". The key indicator is that the greeting ends and waits for the caller to record a message.

2. answering_service - A REAL LIVE PERSON picked up and interacted. The proof is HUMAN CONVERSATION: they ask questions ("how may I help you?", "what is your name?", "are you calling about a new case?"), they react to silence ("hello? is anyone there?"), they have back-and-forth dialogue. A named person answering ("this is Christina") is strong evidence. The key difference from voicemail: a live person RESPONDS and REACTS.

3. human - A real employee or lawyer at the firm answered directly (same as answering_service for our purposes, but this is someone at the actual firm, not a third-party service).

4. ivr_only - An automated phone tree menu ("press 1 for...", "press 2 for...") with no live person reached and no voicemail.

5. no_answer - Nobody/nothing answered. Just ringing, silence, or the call disconnected. Also use this if the ONLY thing heard was a pre-call disclaimer ("this call may be recorded") with no human interaction after it.

6. inconclusive - The call was too short or the transcript is too incomplete to determine what happened. Use this when only a pre-call disclaimer was heard and the call ended before we could tell if anyone would answer.

Respond in EXACTLY this JSON format and nothing else:
{{"answered_by": "category", "is_qualified": true/false, "confidence": "high/medium/low", "notes": "1-2 sentence explanation of what happened on the call"}}

Qualification rules:
- voicemail = TRUE (firm is missing calls - great lead!)
- no_answer = TRUE (nobody picked up at all)
- ivr_only = TRUE (automated menu, no human coverage)
- inconclusive = TRUE (call ended too early, needs retry - but likely no live coverage)
- answering_service = FALSE (firm has live phone coverage)
- human = FALSE (firm has live phone coverage)"""

        resp = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {xai_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "grok-3-fast",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1
            },
            timeout=15
        )
        
        if resp.status_code != 200:
            raise Exception(f"Grok API error {resp.status_code}: {resp.text[:200]}")
        
        content = resp.json()["choices"][0]["message"]["content"].strip()
        
        # Parse JSON from response (handle markdown code blocks)
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        
        result = json.loads(content)
        
        # Ensure required fields
        return {
            "answered_by": result.get("answered_by", "unknown"),
            "is_qualified": result.get("is_qualified", False),
            "confidence": result.get("confidence", "medium"),
            "notes": result.get("notes", "Classified by Grok 4 Fast")
        }
    
    def _fallback_classify(self, transcript: str, end_reason: str, duration: int) -> Dict:
        """Simple fallback if Grok is unavailable."""
        transcript_lower = transcript.lower()
        
        # These are just disclaimers - strip them out before analyzing
        disclaimer_phrases = ["this call may be recorded", "this call is recorded", "this call will be recorded",
                              "this call may be monitored", "for quality assurance", "for quality purposes",
                              "for training purposes", "for quality and training"]
        cleaned = transcript_lower
        for phrase in disclaimer_phrases:
            cleaned = cleaned.replace(phrase, "")
        cleaned = cleaned.strip()
        
        voicemail_words = ["leave a message", "after the beep", "voicemail", "not available", "mailbox", "at the tone", "leave your name"]
        # Real human interaction indicators (not disclaimers)
        live_person_words = ["how may i help", "how can i help", "is anyone there", "hello?",
                             "are you calling about", "what is your name", "can i get your name",
                             "what is this regarding", "i'll transfer", "let me connect"]
        
        if any(w in cleaned for w in live_person_words):
            return {"answered_by": "answering_service", "is_qualified": False, "confidence": "medium", "notes": "Live person detected (fallback classifier)"}
        elif any(w in cleaned for w in voicemail_words):
            return {"answered_by": "voicemail", "is_qualified": True, "confidence": "medium", "notes": "Voicemail detected (fallback classifier)"}
        elif not cleaned or len(cleaned) < 10:
            return {"answered_by": "inconclusive", "is_qualified": True, "confidence": "low", "notes": "Only disclaimers heard, call ended too early (fallback) - retry needed"}
        else:
            return {"answered_by": "unknown", "is_qualified": False, "confidence": "low", "notes": "Could not classify (fallback) - manual review needed"}


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
            'summary',             # What happened step by step
            'transcript',          # Full transcript of what was heard
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
                analysis.get('summary', ''),
                r.get('transcript', '').strip(),
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
        
        try:
            result = caller.make_call(lead['phone'], lead['name'])
        except Exception as e:
            print(f"   ❌ Call failed: {e}")
            result = {"status": "error", "error": str(e), "phone": lead['phone'], "business_name": lead['name']}
        
        result['location'] = lead.get('location', '')
        result['is_24h'] = lead.get('is_24h', False)
        results.append(result)
        
        # Show result
        analysis = result.get('analysis', {})
        answered_by = analysis.get('answered_by', 'unknown')
        is_qualified = analysis.get('is_qualified', False)
        
        stats['total'] += 1
        
        summary = analysis.get('summary', '')
        if is_qualified:
            print(f"   ✅ QUALIFIED - {analysis.get('notes', '')}")
            print(f"      {summary}")
            stats['qualified'] += 1
        elif answered_by == 'human':
            print(f"   👤 Human answered")
            print(f"      {summary}")
            stats['answered'] += 1
        elif answered_by == 'answering_service':
            print(f"   🏢 Answering service")
            print(f"      {summary}")
            stats['service'] += 1
        else:
            print(f"   ❓ {answered_by}")
            print(f"      {summary}")
            stats['failed'] += 1
        
        # Auto-save every 25 calls so we don't lose progress
        if i % 25 == 0:
            print(f"\n   💾 Auto-saving progress ({i}/{len(leads)})...")
            save_results(results)
        
        # Delay between calls
        if i < len(leads):
            print(f"   ⏳ Waiting {delay}s...")
            time.sleep(delay)
    
    # Final save
    print(f"\n💾 Saving final results...")
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


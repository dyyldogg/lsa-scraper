"""
Caller module for audit calls.
Bridges CLI to the Vapi caller implementation.
"""
import sys
from pathlib import Path

# Add parent directory to path to import vapi_caller
sys.path.insert(0, str(Path(__file__).parent.parent))

from .database import Lead, CallAudit, LeadStatus, CallOutcome, get_session
from .config import VAPI_API_KEY, VAPI_PHONE_ID

try:
    from vapi_caller import VapiCaller, load_leads, save_results
except ImportError:
    # Fallback if vapi_caller not available
    VapiCaller = None


class AuditCaller:
    """
    Wrapper around VapiCaller for CLI compatibility.
    """
    
    def __init__(self):
        if not VAPI_API_KEY:
            raise ValueError("VAPI_API_KEY not set. Copy env.example to .env and add your key.")
        if not VAPI_PHONE_ID:
            raise ValueError("VAPI_PHONE_ID not set. Add it to .env")
        
        if VapiCaller is None:
            raise ValueError("vapi_caller.py not found. Make sure it's in the project root.")
        
        self.vapi_caller = VapiCaller()
        self.vapi_caller.create_assistant()
        self.session = get_session()
    
    def get_leads_for_calling(self, only_24_7: bool = True, limit: int = 100):
        """Get leads ready for calling."""
        query = self.session.query(Lead).filter(
            Lead.status == LeadStatus.NEW,
            Lead.phone_number.isnot(None)
        )
        
        if only_24_7:
            query = query.filter(Lead.claims_24_7 == True)
        
        leads = query.limit(limit).all()
        
        # Convert to format expected by vapi_caller
        return [{
            'phone': lead.phone_number,
            'name': lead.name,
            'location': f"{lead.city}, {lead.state}" if lead.city else lead.full_address or "",
            'is_24h': lead.claims_24_7 or False
        } for lead in leads]
    
    def run_audit_batch(
        self,
        only_24_7: bool = True,
        limit: int = 10,
        delay_between_calls: int = 5
    ):
        """Run a batch of audit calls."""
        from vapi_caller import run_audit
        
        leads = self.get_leads_for_calling(only_24_7=only_24_7, limit=limit)
        
        if not leads:
            print("No leads found to call.")
            return
        
        run_audit(
            leads=leads,
            limit=limit,
            only_24h=only_24_7,
            delay=delay_between_calls,
            force_new_ai=False
        )
    
    def make_audit_call(self, lead: Lead):
        """Make a single audit call to a lead."""
        result = self.vapi_caller.make_call(lead.phone_number, lead.name)
        
        # Create CallAudit record
        analysis = result.get('analysis', {})
        outcome_map = {
            'voicemail': CallOutcome.VOICEMAIL,
            'no_answer': CallOutcome.NO_ANSWER,
            'human': CallOutcome.ANSWERED,
            'answering_service': CallOutcome.ANSWERED,
            'busy': CallOutcome.BUSY,
        }
        
        audit = CallAudit(
            lead_id=lead.id,
            phone_number_called=lead.phone_number,
            call_initiated_at=result.get('call_time'),
            outcome=outcome_map.get(analysis.get('answered_by'), CallOutcome.UNKNOWN),
            notes=analysis.get('notes', '')
        )
        
        # Update lead status
        if analysis.get('is_qualified'):
            lead.status = LeadStatus.QUALIFIED
        else:
            lead.status = LeadStatus.DISQUALIFIED
        
        self.session.add(audit)
        self.session.commit()
        
        return audit
    
    def close(self):
        """Close resources."""
        self.session.close()


class MockAuditCaller:
    """
    Mock caller for testing without making real calls.
    """
    
    def __init__(self):
        self.session = get_session()
    
    def get_leads_for_calling(self, only_24_7: bool = True, limit: int = 100):
        """Get leads ready for calling."""
        query = self.session.query(Lead).filter(
            Lead.status == LeadStatus.NEW,
            Lead.phone_number.isnot(None)
        )
        
        if only_24_7:
            query = query.filter(Lead.claims_24_7 == True)
        
        leads = query.limit(limit).all()
        
        return [{
            'phone': lead.phone_number,
            'name': lead.name,
            'location': f"{lead.city}, {lead.state}" if lead.city else lead.full_address or "",
            'is_24h': lead.claims_24_7 or False
        } for lead in leads]
    
    def run_audit_batch(
        self,
        only_24_7: bool = True,
        limit: int = 10,
        delay_between_calls: int = 5
    ):
        """Mock batch - just prints what would happen."""
        leads = self.get_leads_for_calling(only_24_7=only_24_7, limit=limit)
        
        print(f"[MOCK] Would call {len(leads)} leads:")
        for i, lead in enumerate(leads[:5], 1):
            print(f"  {i}. {lead['name']} - {lead['phone']}")
        if len(leads) > 5:
            print(f"  ... and {len(leads) - 5} more")
        print("\n[MOCK] Use without --mock flag to make real calls.")
    
    def make_audit_call(self, lead: Lead):
        """Mock single call."""
        from datetime import datetime
        
        print(f"[MOCK] Would call {lead.name} at {lead.phone_number}")
        
        # Create a mock audit record
        audit = CallAudit(
            lead_id=lead.id,
            phone_number_called=lead.phone_number,
            call_initiated_at=datetime.utcnow(),
            outcome=CallOutcome.UNKNOWN,
            notes="Mock call - no real call made"
        )
        
        self.session.add(audit)
        self.session.commit()
        
        return audit
    
    def close(self):
        """Close resources."""
        self.session.close()


def run_audit(*args, **kwargs):
    """Legacy function - redirects to VapiCaller."""
    from vapi_caller import run_audit as vapi_run_audit
    return vapi_run_audit(*args, **kwargs)

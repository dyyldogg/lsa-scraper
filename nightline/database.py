"""
Database models and session management for Nightline.
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, Float, ForeignKey, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

from .config import DATABASE_URL

# Create engine and session
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class LeadStatus(str, Enum):
    """Status of a lead in the pipeline."""
    NEW = "new"                    # Just scraped, not yet called
    SCHEDULED = "scheduled"        # Call scheduled
    CALLED = "called"              # Call attempted
    QUALIFIED = "qualified"        # Didn't answer - high priority lead!
    DISQUALIFIED = "disqualified"  # Answered - low priority
    CONTACTED = "contacted"        # We've reached out for sales
    CONVERTED = "converted"        # Became a customer


class CallOutcome(str, Enum):
    """Outcome of an audit call."""
    ANSWERED = "answered"          # Human picked up
    VOICEMAIL = "voicemail"        # Went to voicemail
    NO_ANSWER = "no_answer"        # Rang but no answer, no voicemail
    BUSY = "busy"                  # Line was busy
    FAILED = "failed"              # Call failed to connect
    UNKNOWN = "unknown"            # Couldn't determine


class Lead(Base):
    """
    A business lead scraped from Google Maps or Google Local Services Ads.
    """
    __tablename__ = "leads"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Business Info
    business_id = Column(String(255), unique=True, index=True)  # Google Maps business ID or LSA slug
    name = Column(String(500), nullable=False)
    phone_number = Column(String(50), index=True)
    website = Column(String(500))
    full_address = Column(String(1000))
    city = Column(String(255), index=True)
    state = Column(String(100), index=True)
    zipcode = Column(String(20))
    
    # Google Maps Data
    rating = Column(Float)
    review_count = Column(Integer)
    business_type = Column(String(255))
    
    # Industry & Source
    industry = Column(String(100), index=True, default="hvac")  # e.g., "hvac", "pi", "plumber"
    source_type = Column(String(50), default="google_maps")  # "lsa" (Local Services Ads) or "google_maps"
    is_sponsored = Column(Boolean, default=False)  # True if from LSA sponsored listing
    google_guaranteed = Column(Boolean, default=False)  # True if Google Guaranteed badge
    years_in_business = Column(String(50))  # e.g., "15+ years"
    
    # Hours & Availability Claims
    hours_json = Column(Text)  # JSON string of operating hours
    claims_24_7 = Column(Boolean, default=False)
    availability_keywords_found = Column(Text)  # Comma-separated keywords found
    
    # Lead Management
    status = Column(SQLEnum(LeadStatus), default=LeadStatus.NEW, index=True)
    source_query = Column(String(255))  # The search query that found this lead
    source_region = Column(String(100))  # Geographic region searched
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    call_audits = relationship("CallAudit", back_populates="lead", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Lead(id={self.id}, name='{self.name}', industry='{self.industry}', status={self.status.value})>"


class CallAudit(Base):
    """
    Record of an audit call to test if a business answers.
    """
    __tablename__ = "call_audits"
    
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    
    # Call Details
    twilio_call_sid = Column(String(100), unique=True)
    phone_number_called = Column(String(50))
    
    # Timing
    call_initiated_at = Column(DateTime, nullable=False)
    call_ended_at = Column(DateTime)
    call_duration_seconds = Column(Integer)
    
    # Outcome
    outcome = Column(SQLEnum(CallOutcome), default=CallOutcome.UNKNOWN, index=True)
    answered_by = Column(String(50))  # 'human', 'machine', 'unknown'
    rings_before_answer = Column(Integer)
    
    # Context
    time_of_day = Column(String(20))  # 'morning', 'afternoon', 'evening', 'night'
    day_of_week = Column(String(20))  # 'monday', 'tuesday', etc.
    is_business_hours = Column(Boolean)  # Was this during their stated hours?
    
    # Recording/Notes
    recording_url = Column(String(500))
    notes = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    lead = relationship("Lead", back_populates="call_audits")
    
    def __repr__(self):
        return f"<CallAudit(id={self.id}, lead_id={self.lead_id}, outcome={self.outcome.value})>"


class ScrapeRun(Base):
    """
    Record of a scraping session.
    """
    __tablename__ = "scrape_runs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Search Parameters
    query = Column(String(500))
    region = Column(String(100))
    
    # Results
    businesses_found = Column(Integer, default=0)
    new_leads_added = Column(Integer, default=0)
    duplicates_skipped = Column(Integer, default=0)
    
    # Timing
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    
    # Status
    status = Column(String(50), default="running")  # running, completed, failed
    error_message = Column(Text)


def init_db():
    """Initialize the database, creating all tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session():
    """Get a database session (non-generator version)."""
    return SessionLocal()


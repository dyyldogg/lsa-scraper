"""
Lead scraper for finding HVAC businesses claiming 24/7 service.
Uses Google Maps Local Business Data API via RapidAPI.
"""
import json
import re
from datetime import datetime
from typing import Optional, List, Dict, Any
import httpx
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .config import (
    RAPIDAPI_KEY, 
    RAPIDAPI_HOST, 
    DEFAULT_SEARCH_QUERIES,
    AVAILABILITY_KEYWORDS
)
from .database import Lead, ScrapeRun, LeadStatus, get_session, init_db

console = Console()


class HVACLeadScraper:
    """
    Scrapes Google Maps for HVAC businesses claiming 24/7 availability.
    """
    
    def __init__(self):
        self.api_key = RAPIDAPI_KEY
        self.base_url = "https://local-business-data.p.rapidapi.com"
        self.headers = {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": RAPIDAPI_HOST
        }
        self.session = get_session()
    
    def search_businesses(
        self, 
        query: str, 
        region: str = "us",
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search for businesses matching the query.
        
        Args:
            query: Search query (e.g., "24/7 HVAC repair in Denver, CO")
            region: Country/region code
            lat: Latitude for location bias
            lng: Longitude for location bias
            limit: Maximum results to return
        
        Returns:
            List of business data dictionaries
        """
        params = {
            "query": query,
            "region": region,
            "limit": str(limit),
            "language": "en",
            "extract_emails_and_contacts": "false"
        }
        
        if lat and lng:
            params["lat"] = str(lat)
            params["lng"] = str(lng)
        
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{self.base_url}/search",
                    headers=self.headers,
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                return data.get("data", [])
        except httpx.HTTPError as e:
            console.print(f"[red]API Error: {e}[/red]")
            return []
    
    def get_business_details(self, business_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific business.
        
        Args:
            business_id: Google Maps business ID or place_id
        
        Returns:
            Business details dictionary or None
        """
        params = {
            "business_id": business_id,
            "extract_emails_and_contacts": "true",
            "language": "en",
            "region": "us"
        }
        
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{self.base_url}/business-details",
                    headers=self.headers,
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                return data.get("data", [{}])[0] if data.get("data") else None
        except httpx.HTTPError as e:
            console.print(f"[red]API Error getting details: {e}[/red]")
            return None
    
    def check_24_7_claims(self, business: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Check if a business claims to be available 24/7.
        
        Args:
            business: Business data dictionary
        
        Returns:
            Tuple of (claims_24_7, list of keywords found)
        """
        keywords_found = []
        
        # Check business name
        name = business.get("name", "").lower()
        
        # Check description/about
        description = business.get("about", {}).get("summary", "").lower() if business.get("about") else ""
        
        # Check working hours
        hours = business.get("working_hours", {})
        hours_text = json.dumps(hours).lower() if hours else ""
        
        # Combine all text to search
        all_text = f"{name} {description} {hours_text}"
        
        for keyword in AVAILABILITY_KEYWORDS:
            if keyword.lower() in all_text:
                keywords_found.append(keyword)
        
        # Also check if any day shows 24 hours
        if hours:
            for day, times in hours.items():
                if times and isinstance(times, list):
                    for time_range in times:
                        if "24 hours" in str(time_range).lower() or "open 24" in str(time_range).lower():
                            if "24 hours" not in keywords_found:
                                keywords_found.append("24 hours (in schedule)")
        
        return len(keywords_found) > 0, keywords_found
    
    def business_to_lead(
        self, 
        business: Dict[str, Any], 
        source_query: str,
        source_region: str
    ) -> Optional[Lead]:
        """
        Convert a business API response to a Lead model.
        
        Args:
            business: Business data from API
            source_query: The search query used
            source_region: The region searched
        
        Returns:
            Lead object or None if invalid
        """
        business_id = business.get("business_id") or business.get("place_id")
        phone = business.get("phone_number")
        
        if not business_id or not phone:
            return None
        
        # Check for 24/7 claims
        claims_24_7, keywords = self.check_24_7_claims(business)
        
        # Parse address components
        address = business.get("full_address", "")
        city = business.get("city", "")
        state = business.get("state", "")
        zipcode = business.get("zipcode", "") or business.get("postal_code", "")
        
        # If city/state not directly available, try to parse from address
        if not city and address:
            # Simple parsing - this could be improved
            parts = address.split(",")
            if len(parts) >= 2:
                city = parts[-2].strip() if len(parts) > 2 else ""
        
        lead = Lead(
            business_id=business_id,
            name=business.get("name", "Unknown"),
            phone_number=phone,
            website=business.get("website"),
            full_address=address,
            city=city,
            state=state,
            zipcode=zipcode,
            rating=business.get("rating"),
            review_count=business.get("review_count"),
            business_type=business.get("type"),
            hours_json=json.dumps(business.get("working_hours")) if business.get("working_hours") else None,
            claims_24_7=claims_24_7,
            availability_keywords_found=",".join(keywords) if keywords else None,
            source_query=source_query,
            source_region=source_region,
            status=LeadStatus.NEW
        )
        
        return lead
    
    def scrape_city(
        self, 
        city: str, 
        state: str,
        queries: Optional[List[str]] = None,
        limit_per_query: int = 50
    ) -> Dict[str, int]:
        """
        Scrape HVAC leads for a specific city.
        
        Args:
            city: City name
            state: State name or abbreviation
            queries: List of search queries (defaults to standard queries)
            limit_per_query: Max results per query
        
        Returns:
            Dict with scraping statistics
        """
        if queries is None:
            queries = DEFAULT_SEARCH_QUERIES
        
        region = f"{city}, {state}"
        stats = {
            "total_found": 0,
            "new_leads": 0,
            "duplicates": 0,
            "no_phone": 0,
            "claims_24_7": 0
        }
        
        console.print(f"\n[bold blue]🔍 Scraping HVAC leads in {region}[/bold blue]\n")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            for query in queries:
                full_query = f"{query} in {region}"
                task = progress.add_task(f"Searching: {query}...", total=None)
                
                businesses = self.search_businesses(
                    query=full_query,
                    limit=limit_per_query
                )
                
                stats["total_found"] += len(businesses)
                progress.update(task, description=f"Found {len(businesses)} for '{query}'")
                
                for biz in businesses:
                    lead = self.business_to_lead(biz, query, region)
                    
                    if not lead:
                        stats["no_phone"] += 1
                        continue
                    
                    # Check if already exists
                    existing = self.session.query(Lead).filter_by(
                        business_id=lead.business_id
                    ).first()
                    
                    if existing:
                        stats["duplicates"] += 1
                        continue
                    
                    # Add new lead
                    self.session.add(lead)
                    stats["new_leads"] += 1
                    
                    if lead.claims_24_7:
                        stats["claims_24_7"] += 1
                
                self.session.commit()
                progress.remove_task(task)
        
        # Print summary
        console.print(f"\n[bold green]✅ Scraping Complete for {region}[/bold green]")
        console.print(f"   Total businesses found: {stats['total_found']}")
        console.print(f"   New leads added: {stats['new_leads']}")
        console.print(f"   Duplicates skipped: {stats['duplicates']}")
        console.print(f"   [yellow]Claiming 24/7: {stats['claims_24_7']}[/yellow]")
        
        return stats
    
    def scrape_multiple_cities(
        self,
        cities: List[tuple[str, str]],  # List of (city, state) tuples
        queries: Optional[List[str]] = None,
        limit_per_query: int = 50
    ) -> Dict[str, Dict[str, int]]:
        """
        Scrape HVAC leads across multiple cities.
        
        Args:
            cities: List of (city, state) tuples
            queries: Search queries to use
            limit_per_query: Max results per query per city
        
        Returns:
            Dict mapping city names to their stats
        """
        all_stats = {}
        
        for city, state in cities:
            stats = self.scrape_city(city, state, queries, limit_per_query)
            all_stats[f"{city}, {state}"] = stats
        
        # Print grand total
        total_new = sum(s["new_leads"] for s in all_stats.values())
        total_24_7 = sum(s["claims_24_7"] for s in all_stats.values())
        
        console.print(f"\n[bold magenta]📊 Grand Total Across All Cities[/bold magenta]")
        console.print(f"   New leads: {total_new}")
        console.print(f"   Claiming 24/7: {total_24_7}")
        
        return all_stats
    
    def get_leads_for_calling(
        self, 
        only_24_7_claims: bool = True,
        limit: int = 100
    ) -> List[Lead]:
        """
        Get leads that are ready for audit calls.
        
        Args:
            only_24_7_claims: Only return leads claiming 24/7 service
            limit: Maximum number to return
        
        Returns:
            List of Lead objects
        """
        query = self.session.query(Lead).filter(
            Lead.status == LeadStatus.NEW,
            Lead.phone_number.isnot(None)
        )
        
        if only_24_7_claims:
            query = query.filter(Lead.claims_24_7 == True)
        
        return query.limit(limit).all()
    
    def close(self):
        """Close the database session."""
        self.session.close()


# Convenience function for quick scraping
def quick_scrape(city: str, state: str, limit: int = 50) -> Dict[str, int]:
    """
    Quick function to scrape a single city.
    
    Args:
        city: City name
        state: State abbreviation
        limit: Max results per query
    
    Returns:
        Scraping statistics
    """
    init_db()
    scraper = HVACLeadScraper()
    try:
        return scraper.scrape_city(city, state, limit_per_query=limit)
    finally:
        scraper.close()


"""
Google Local Services Ads (LSA) Scraper.

Scrapes sponsored business listings from Google's Local Services page
(google.com/localservices/prolist) using Playwright browser automation.

Supports any industry and any location - just configure in config.py.
"""
import asyncio
import hashlib
import json
import random
import re
import time
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import quote_plus

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.panel import Panel

from .config import (
    INDUSTRIES,
    CALIFORNIA_CITIES,
    ALL_CALIFORNIA_CITIES,
    LSA_PAGE_LOAD_TIMEOUT,
    LSA_SCROLL_DELAY,
    LSA_MAX_SCROLLS,
    get_industry_config,
    get_cities_for_region,
)
from .database import Lead, ScrapeRun, LeadStatus, get_session, init_db

console = Console()


def _generate_business_id(name: str, city: str, state: str) -> str:
    """Generate a unique ID for an LSA business based on name + location."""
    raw = f"{name.lower().strip()}:{city.lower().strip()}:{state.lower().strip()}"
    return f"lsa_{hashlib.md5(raw.encode()).hexdigest()[:16]}"


def _clean_phone(text: str) -> Optional[str]:
    """Extract and clean a US phone number from text."""
    # Look for patterns like (213) 555-1234, 213-555-1234, 2135551234
    patterns = [
        r'\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4}',
        r'\+1\s?\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4}',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            digits = re.sub(r'\D', '', match.group())
            if len(digits) == 10:
                return f"+1{digits}"
            elif len(digits) == 11 and digits.startswith('1'):
                return f"+{digits}"
    return None


def _parse_review_count(text: str) -> Optional[int]:
    """Parse review count from text like '(123)' or '123 reviews'."""
    match = re.search(r'(\d[\d,]*)', text)
    if match:
        return int(match.group(1).replace(',', ''))
    return None


def _parse_rating(text: str) -> Optional[float]:
    """Parse rating from text like '4.8' or '4.8 stars'."""
    match = re.search(r'(\d\.\d)', text)
    if match:
        return float(match.group(1))
    return None


class LSAScraper:
    """
    Scrapes Google Local Services Ads (sponsored listings) for any industry.
    
    Uses Playwright to render the JavaScript-heavy LSA pages and extract
    business data from the sponsored results.
    """
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.session = get_session()
        self._browser = None
        self._playwright = None
    
    async def _get_browser(self):
        """Lazy-initialize the browser."""
        if self._browser is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                ]
            )
        return self._browser
    
    async def _new_page(self):
        """Create a new browser page with stealth settings."""
        browser = await self._get_browser()
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/Los_Angeles",
        )
        page = await context.new_page()
        
        # Remove webdriver detection
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
        """)
        
        return page
    
    def _build_lsa_url(self, query: str, location: str) -> str:
        """Build a Google Local Services URL."""
        full_query = f"{query} near {location}"
        return (
            f"https://www.google.com/localservices/prolist"
            f"?src=2&q={quote_plus(full_query)}"
        )
    
    async def _scroll_for_results(self, page, max_scrolls: int = None):
        """Scroll the page to load more LSA results."""
        if max_scrolls is None:
            max_scrolls = LSA_MAX_SCROLLS
        
        last_count = 0
        for i in range(max_scrolls):
            # Count current results
            cards = await page.query_selector_all('[data-profile-url-path], [class*="xYjf2e"], .ykYNg')
            current_count = len(cards)
            
            if current_count == last_count and i > 2:
                # No new results loaded, stop scrolling
                break
            
            last_count = current_count
            
            # Scroll down
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(LSA_SCROLL_DELAY + random.uniform(0.3, 0.8))
        
        return last_count
    
    async def _extract_businesses_from_page(self, page) -> List[Dict[str, Any]]:
        """
        Extract business data from the LSA page.
        
        This tries multiple selector strategies since Google's HTML structure
        can vary. Falls back gracefully if selectors change.
        """
        businesses = []
        
        # Strategy 1: Try the main business card containers
        # Google LSA uses various class names - try multiple approaches
        cards = await page.query_selector_all('[data-profile-url-path]')
        
        if not cards:
            # Strategy 2: Try aria-based selectors
            cards = await page.query_selector_all('[role="listitem"]')
        
        if not cards:
            # Strategy 3: Try common LSA card class patterns
            cards = await page.query_selector_all('.xYjf2e, .ykYNg, .c7fp0b')
        
        if not cards:
            # Strategy 4: Broad fallback - get the accessibility tree
            return await self._extract_from_accessibility_tree(page)
        
        for card in cards:
            try:
                biz = await self._parse_business_card(card)
                if biz and biz.get("name"):
                    businesses.append(biz)
            except Exception:
                continue
        
        return businesses
    
    async def _parse_business_card(self, card) -> Optional[Dict[str, Any]]:
        """Parse a single business card element into a data dict."""
        biz = {}
        
        # Try to get the full text content of the card
        text_content = await card.inner_text()
        
        if not text_content or len(text_content.strip()) < 5:
            return None
        
        lines = [l.strip() for l in text_content.split('\n') if l.strip()]
        
        if not lines:
            return None
        
        # Business name - usually the first prominent text
        # Try heading elements first
        name_el = await card.query_selector('div[role="heading"], h2, h3, .rgnuSb, .xJVozb, [data-name]')
        if name_el:
            biz["name"] = (await name_el.inner_text()).strip()
        else:
            # First non-trivial line is usually the name
            for line in lines:
                if len(line) > 2 and not line.startswith('Sponsored') and not re.match(r'^[\d\.\(\)]+$', line):
                    biz["name"] = line
                    break
        
        if not biz.get("name"):
            return None
        
        # Check for sponsored badge
        biz["is_sponsored"] = "Sponsored" in text_content or "Ad" in text_content[:20]
        
        # Check for Google Guaranteed
        biz["google_guaranteed"] = any(
            kw in text_content for kw in ["Google Guaranteed", "Google guaranteed", "Google Screened", "Guaranteed"]
        )
        
        # Rating
        rating_el = await card.query_selector('[role="img"][aria-label*="star"], .pNFZHb, .rGaJuf')
        if rating_el:
            aria = await rating_el.get_attribute("aria-label") or ""
            biz["rating"] = _parse_rating(aria or await rating_el.inner_text())
        else:
            biz["rating"] = _parse_rating(text_content)
        
        # Review count
        review_el = await card.query_selector('.leIgTe, .QwSaG, .hGz87c')
        if review_el:
            biz["review_count"] = _parse_review_count(await review_el.inner_text())
        else:
            # Look for patterns like "(123)" or "123 reviews"
            review_match = re.search(r'\((\d[\d,]*)\)', text_content)
            if review_match:
                biz["review_count"] = int(review_match.group(1).replace(',', ''))
        
        # Phone number
        phone_el = await card.query_selector('[data-phone-number], a[href^="tel:"]')
        if phone_el:
            phone_attr = await phone_el.get_attribute("data-phone-number") or await phone_el.get_attribute("href") or ""
            biz["phone_number"] = _clean_phone(phone_attr) or _clean_phone(text_content)
        else:
            biz["phone_number"] = _clean_phone(text_content)
        
        # Years in business
        years_match = re.search(r'(\d+\+?\s*(?:years?|yrs?))\s*(?:in business)?', text_content, re.IGNORECASE)
        if years_match:
            biz["years_in_business"] = years_match.group(1)
        
        # Profile URL (useful for deduplication)
        profile_url = await card.evaluate("el => el.getAttribute('data-profile-url-path')") if card else None
        if profile_url:
            biz["profile_url"] = profile_url
        
        return biz
    
    async def _extract_from_accessibility_tree(self, page) -> List[Dict[str, Any]]:
        """
        Fallback: extract businesses from the page's accessibility tree.
        This is more robust against HTML structure changes.
        """
        businesses = []
        
        # Get all text content and parse it
        content = await page.content()
        text = await page.inner_text("body")
        
        # Look for phone number patterns as anchors for business entries
        phone_pattern = re.compile(r'\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4}')
        
        # Split content into sections around phone numbers
        parts = phone_pattern.split(text)
        phones = phone_pattern.findall(text)
        
        for i, phone_raw in enumerate(phones):
            phone = _clean_phone(phone_raw)
            if not phone:
                continue
            
            # Get the text before this phone number
            context = parts[i] if i < len(parts) else ""
            context_lines = [l.strip() for l in context.split('\n') if l.strip()]
            
            if not context_lines:
                continue
            
            # Try to find the business name (usually a few lines before the phone)
            name = None
            for line in reversed(context_lines[-5:]):
                if len(line) > 3 and not re.match(r'^[\d\.\(\)\+\-\s]+$', line):
                    name = line
                    break
            
            if name:
                businesses.append({
                    "name": name,
                    "phone_number": phone,
                    "is_sponsored": True,  # If it's on the LSA page, it's sponsored
                    "google_guaranteed": "Guaranteed" in context or "Screened" in context,
                    "rating": _parse_rating(context),
                    "review_count": _parse_review_count(context),
                })
        
        return businesses
    
    async def scrape_lsa_page(
        self,
        industry_key: str,
        city: str,
        state: str,
        query: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Scrape a single LSA page for a given industry and location.
        
        Args:
            industry_key: Key from INDUSTRIES config (e.g., "pi", "hvac")
            city: City name
            state: State abbreviation
            query: Optional specific query (overrides industry default)
        
        Returns:
            List of business data dictionaries
        """
        industry = get_industry_config(industry_key)
        location = f"{city}, {state}"
        search_query = query or industry["lsa_queries"][0]
        
        url = self._build_lsa_url(search_query, location)
        
        page = await self._new_page()
        
        try:
            # Navigate to LSA page
            await page.goto(url, wait_until="domcontentloaded", timeout=LSA_PAGE_LOAD_TIMEOUT)
            
            # Wait for results to appear (try multiple selectors)
            try:
                await page.wait_for_selector(
                    '[data-profile-url-path], [role="listitem"], .xYjf2e, .ykYNg',
                    timeout=10000
                )
            except Exception:
                # Page might have loaded differently, continue anyway
                pass
            
            # Small random delay to seem human
            await asyncio.sleep(random.uniform(1.5, 3.0))
            
            # Scroll to load more results
            await self._scroll_for_results(page)
            
            # Extract businesses
            businesses = await self._extract_businesses_from_page(page)
            
            # Tag each business with metadata
            for biz in businesses:
                biz["industry"] = industry_key
                biz["city"] = city
                biz["state"] = state
                biz["source_query"] = search_query
                biz["source_url"] = url
                biz["scraped_at"] = datetime.utcnow().isoformat()
            
            return businesses
            
        except Exception as e:
            console.print(f"[red]Error scraping {search_query} in {location}: {e}[/red]")
            return []
        finally:
            await page.close()
    
    def _business_to_lead(
        self,
        biz: Dict[str, Any],
        industry_key: str,
    ) -> Optional[Lead]:
        """Convert a scraped business dict to a Lead model."""
        name = biz.get("name", "").strip()
        city = biz.get("city", "")
        state = biz.get("state", "")
        
        if not name:
            return None
        
        # Generate a unique business ID
        business_id = biz.get("profile_url") or _generate_business_id(name, city, state)
        
        # Check availability keywords
        industry = get_industry_config(industry_key)
        text_to_check = name.lower()
        keywords_found = [
            kw for kw in industry["availability_keywords"]
            if kw.lower() in text_to_check
        ]
        
        lead = Lead(
            business_id=business_id,
            name=name,
            phone_number=biz.get("phone_number"),
            city=city,
            state=state,
            rating=biz.get("rating"),
            review_count=biz.get("review_count"),
            business_type=industry["name"],
            industry=industry_key,
            source_type="lsa",
            is_sponsored=biz.get("is_sponsored", True),
            google_guaranteed=biz.get("google_guaranteed", False),
            years_in_business=biz.get("years_in_business"),
            claims_24_7=len(keywords_found) > 0,
            availability_keywords_found=",".join(keywords_found) if keywords_found else None,
            source_query=biz.get("source_query", ""),
            source_region=f"{city}, {state}",
            status=LeadStatus.NEW,
        )
        
        return lead
    
    async def scrape_industry_city(
        self,
        industry_key: str,
        city: str,
        state: str,
        max_queries: Optional[int] = None,
    ) -> Dict[str, int]:
        """
        Scrape all LSA queries for one industry in one city.
        
        Args:
            industry_key: Industry key (e.g., "pi")
            city: City name
            state: State abbreviation
            max_queries: Limit number of queries to run (None = all)
        
        Returns:
            Stats dict with counts
        """
        industry = get_industry_config(industry_key)
        queries = industry["lsa_queries"]
        if max_queries:
            queries = queries[:max_queries]
        
        location = f"{city}, {state}"
        stats = {
            "total_found": 0,
            "new_leads": 0,
            "duplicates": 0,
            "no_name": 0,
            "sponsored": 0,
        }
        
        for query in queries:
            businesses = await self.scrape_lsa_page(industry_key, city, state, query)
            stats["total_found"] += len(businesses)
            
            for biz in businesses:
                lead = self._business_to_lead(biz, industry_key)
                
                if not lead:
                    stats["no_name"] += 1
                    continue
                
                # Check for duplicates
                existing = self.session.query(Lead).filter_by(
                    business_id=lead.business_id
                ).first()
                
                if existing:
                    stats["duplicates"] += 1
                    continue
                
                self.session.add(lead)
                stats["new_leads"] += 1
                
                if lead.is_sponsored:
                    stats["sponsored"] += 1
            
            self.session.commit()
            
            # Random delay between queries to avoid rate limiting
            await asyncio.sleep(random.uniform(2.0, 4.0))
        
        return stats
    
    async def scrape_industry_region(
        self,
        industry_key: str,
        region: Optional[str] = None,
        cities: Optional[List[Tuple[str, str]]] = None,
        max_queries_per_city: Optional[int] = 3,
    ) -> Dict[str, Dict[str, int]]:
        """
        Scrape an industry across a whole region or custom city list.
        
        Args:
            industry_key: Industry key (e.g., "pi")
            region: California region key (e.g., "los_angeles_metro") or None
            cities: Custom list of (city, state) tuples (overrides region)
            max_queries_per_city: Max queries per city (to manage rate limits)
        
        Returns:
            Dict mapping city names to stats
        """
        if cities is None:
            if region:
                cities = get_cities_for_region(region)
            else:
                cities = ALL_CALIFORNIA_CITIES
        
        industry = get_industry_config(industry_key)
        all_stats = {}
        
        console.print(Panel.fit(
            f"[bold cyan]LSA Scraper[/bold cyan]\n"
            f"Industry: [bold]{industry['name']}[/bold]\n"
            f"Cities: [bold]{len(cities)}[/bold]\n"
            f"Queries per city: [bold]{max_queries_per_city or 'all'}[/bold]",
            title="Nightline LSA Scraper",
        ))
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Scraping {industry['name']} LSA...",
                total=len(cities),
            )
            
            for city, state in cities:
                location = f"{city}, {state}"
                progress.update(task, description=f"Scraping {location}...")
                
                try:
                    stats = await self.scrape_industry_city(
                        industry_key, city, state,
                        max_queries=max_queries_per_city,
                    )
                    all_stats[location] = stats
                    
                    if stats["new_leads"] > 0:
                        console.print(
                            f"  [green]+{stats['new_leads']} new leads[/green] "
                            f"from {location} ({stats['total_found']} found, "
                            f"{stats['duplicates']} dupes)"
                        )
                except Exception as e:
                    console.print(f"  [red]Error in {location}: {e}[/red]")
                    all_stats[location] = {"error": str(e)}
                
                progress.advance(task)
                
                # Longer delay between cities
                await asyncio.sleep(random.uniform(3.0, 6.0))
        
        # Print summary
        total_new = sum(
            s.get("new_leads", 0) for s in all_stats.values() if isinstance(s, dict)
        )
        total_found = sum(
            s.get("total_found", 0) for s in all_stats.values() if isinstance(s, dict)
        )
        total_sponsored = sum(
            s.get("sponsored", 0) for s in all_stats.values() if isinstance(s, dict)
        )
        
        console.print(f"\n[bold green]LSA Scrape Complete![/bold green]")
        console.print(f"  Total businesses found: {total_found}")
        console.print(f"  New leads added: {total_new}")
        console.print(f"  Sponsored (LSA): {total_sponsored}")
        
        return all_stats
    
    async def close(self):
        """Close the browser and database session."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self.session.close()


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS (sync wrappers for CLI usage)
# ═══════════════════════════════════════════════════════════════════════════════

def run_lsa_scrape(
    industry: str,
    city: str,
    state: str,
    headless: bool = True,
) -> Dict[str, int]:
    """
    Sync wrapper: scrape LSA for one industry in one city.
    
    Example:
        stats = run_lsa_scrape("pi", "Los Angeles", "CA")
    """
    init_db()
    
    async def _run():
        scraper = LSAScraper(headless=headless)
        try:
            return await scraper.scrape_industry_city(industry, city, state)
        finally:
            await scraper.close()
    
    return asyncio.run(_run())


def run_lsa_region_scrape(
    industry: str,
    region: Optional[str] = None,
    cities: Optional[List[Tuple[str, str]]] = None,
    headless: bool = True,
    max_queries_per_city: int = 3,
) -> Dict[str, Dict[str, int]]:
    """
    Sync wrapper: scrape LSA for one industry across a region.
    
    Examples:
        # Scrape PI firms across all LA metro cities
        stats = run_lsa_region_scrape("pi", region="los_angeles_metro")
        
        # Scrape PI firms across ALL California
        stats = run_lsa_region_scrape("pi")
        
        # Custom city list
        stats = run_lsa_region_scrape("pi", cities=[("Los Angeles", "CA"), ("San Diego", "CA")])
    """
    init_db()
    
    async def _run():
        scraper = LSAScraper(headless=headless)
        try:
            return await scraper.scrape_industry_region(
                industry,
                region=region,
                cities=cities,
                max_queries_per_city=max_queries_per_city,
            )
        finally:
            await scraper.close()
    
    return asyncio.run(_run())


def list_industries():
    """Print available industries."""
    table = Table(title="Available Industries")
    table.add_column("Key", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Queries", style="dim")
    
    for key, config in INDUSTRIES.items():
        table.add_row(
            key,
            config["name"],
            ", ".join(config["lsa_queries"][:3]) + "...",
        )
    
    console.print(table)


def list_regions():
    """Print available California regions and their cities."""
    for region, cities in CALIFORNIA_CITIES.items():
        city_names = ", ".join(f"{c}" for c, s in cities)
        console.print(f"[bold cyan]{region}[/bold cyan]: {city_names}")

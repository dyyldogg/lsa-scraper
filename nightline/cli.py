"""
Command-line interface for Nightline lead generation.
"""
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .database import init_db, get_session, Lead, CallAudit, LeadStatus, CallOutcome
from .scraper import HVACLeadScraper, quick_scrape
from .caller import AuditCaller, MockAuditCaller, run_audit
from .config import INDUSTRIES, CALIFORNIA_CITIES

console = Console()

INDUSTRY_KEYS = list(INDUSTRIES.keys())
REGION_KEYS = list(CALIFORNIA_CITIES.keys())


@click.group()
@click.version_option(version="2.0.0", prog_name="Nightline")
def cli():
    """
    Nightline - Multi-Industry Lead Generation via Google LSA

    Scrape Google Local Services Ads (sponsored listings) for any industry,
    audit-call them, and find businesses that miss calls.
    """
    init_db()


# ═══════════════════════════════════════════════════════════════════════════════
# LSA SCRAPE COMMANDS (NEW - primary scraping method)
# ═══════════════════════════════════════════════════════════════════════════════

@cli.group()
def lsa():
    """Scrape Google Local Services Ads (sponsored listings)."""
    pass


@lsa.command("industries")
def lsa_industries():
    """List all available industries."""
    from .lsa_scraper import list_industries
    list_industries()


@lsa.command("regions")
def lsa_regions():
    """List California regions and their cities."""
    from .lsa_scraper import list_regions
    list_regions()


@lsa.command("city")
@click.argument("industry", type=click.Choice(INDUSTRY_KEYS, case_sensitive=False))
@click.argument("city")
@click.argument("state", default="CA")
@click.option("--queries", "-q", default=3, help="Max queries per city (default: 3)")
@click.option("--visible", is_flag=True, help="Show the browser (non-headless)")
def lsa_city(industry: str, city: str, state: str, queries: int, visible: bool):
    """
    Scrape LSA sponsored listings for one industry in one city.

    Examples:
        nightline lsa city pi "Los Angeles" CA
        nightline lsa city plumber "San Diego" --visible
    """
    from .lsa_scraper import run_lsa_scrape
    
    industry_name = INDUSTRIES[industry]["name"]
    console.print(Panel.fit(
        f"[bold cyan]LSA Scrape[/bold cyan]\n"
        f"Industry: [bold]{industry_name}[/bold]\n"
        f"Location: [bold]{city}, {state}[/bold]\n"
        f"Max queries: {queries}",
        title="Nightline LSA",
    ))
    
    stats = run_lsa_scrape(industry, city, state, headless=not visible)
    console.print(f"\n[green]Done! {stats.get('new_leads', 0)} new leads added.[/green]")


@lsa.command("region")
@click.argument("industry", type=click.Choice(INDUSTRY_KEYS, case_sensitive=False))
@click.argument("region", type=click.Choice(REGION_KEYS, case_sensitive=False))
@click.option("--queries", "-q", default=3, help="Max queries per city (default: 3)")
@click.option("--visible", is_flag=True, help="Show the browser (non-headless)")
def lsa_region(industry: str, region: str, queries: int, visible: bool):
    """
    Scrape LSA for one industry across a California region.

    Examples:
        nightline lsa region pi los_angeles_metro
        nightline lsa region plumber sf_bay_area
        nightline lsa region hvac san_diego
    """
    from .lsa_scraper import run_lsa_region_scrape
    
    industry_name = INDUSTRIES[industry]["name"]
    cities = CALIFORNIA_CITIES[region]
    console.print(Panel.fit(
        f"[bold cyan]LSA Regional Scrape[/bold cyan]\n"
        f"Industry: [bold]{industry_name}[/bold]\n"
        f"Region: [bold]{region}[/bold] ({len(cities)} cities)\n"
        f"Queries per city: {queries}",
        title="Nightline LSA",
    ))
    
    run_lsa_region_scrape(
        industry, region=region,
        headless=not visible,
        max_queries_per_city=queries,
    )


@lsa.command("california")
@click.argument("industry", type=click.Choice(INDUSTRY_KEYS, case_sensitive=False))
@click.option("--queries", "-q", default=2, help="Max queries per city (default: 2)")
@click.option("--visible", is_flag=True, help="Show the browser (non-headless)")
def lsa_california(industry: str, queries: int, visible: bool):
    """
    Scrape LSA for one industry across ALL of California.

    Examples:
        nightline lsa california pi
        nightline lsa california hvac --queries 1
    """
    from .lsa_scraper import run_lsa_region_scrape
    from .config import ALL_CALIFORNIA_CITIES
    
    industry_name = INDUSTRIES[industry]["name"]
    console.print(Panel.fit(
        f"[bold cyan]LSA Statewide Scrape[/bold cyan]\n"
        f"Industry: [bold]{industry_name}[/bold]\n"
        f"Coverage: [bold]ALL California[/bold] ({len(ALL_CALIFORNIA_CITIES)} cities)\n"
        f"Queries per city: {queries}\n"
        f"[yellow]This will take a while...[/yellow]",
        title="Nightline LSA",
    ))
    
    run_lsa_region_scrape(
        industry,
        cities=ALL_CALIFORNIA_CITIES,
        headless=not visible,
        max_queries_per_city=queries,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# LEGACY SCRAPE COMMANDS (Google Maps API via RapidAPI)
# ═══════════════════════════════════════════════════════════════════════════════

@cli.group()
def scrape():
    """[Legacy] Scrape leads from Google Maps API."""
    pass


@scrape.command("city")
@click.argument("city")
@click.argument("state")
@click.option("--limit", "-l", default=50, help="Max results per search query")
@click.option("--query", "-q", multiple=True, help="Custom search queries (can specify multiple)")
def scrape_city(city: str, state: str, limit: int, query: tuple):
    """
    Scrape HVAC leads from a specific city via Google Maps API.
    
    Example: nightline scrape city Denver CO --limit 100
    """
    queries = list(query) if query else None
    
    console.print(Panel.fit(
        f"[bold blue]Scraping HVAC Leads (Maps API)[/bold blue]\n"
        f"City: {city}, {state}\n"
        f"Limit: {limit} per query",
        title="Nightline Scraper"
    ))
    
    scraper = HVACLeadScraper()
    try:
        stats = scraper.scrape_city(city, state, queries=queries, limit_per_query=limit)
    finally:
        scraper.close()


@scrape.command("multi")
@click.option("--cities", "-c", required=True, help="Cities in format 'City1,State1;City2,State2'")
@click.option("--limit", "-l", default=50, help="Max results per search query")
def scrape_multi(cities: str, limit: int):
    """
    Scrape HVAC leads from multiple cities via Google Maps API.
    
    Example: nightline scrape multi -c "Denver,CO;Phoenix,AZ;Dallas,TX"
    """
    city_list = []
    for city_state in cities.split(";"):
        parts = city_state.strip().split(",")
        if len(parts) == 2:
            city_list.append((parts[0].strip(), parts[1].strip()))
    
    if not city_list:
        console.print("[red]Invalid cities format. Use: 'City1,State1;City2,State2'[/red]")
        return
    
    console.print(Panel.fit(
        f"[bold blue]Multi-City Scrape (Maps API)[/bold blue]\n"
        f"Cities: {len(city_list)}\n"
        f"Limit: {limit} per query per city",
        title="Nightline Scraper"
    ))
    
    scraper = HVACLeadScraper()
    try:
        scraper.scrape_multiple_cities(city_list, limit_per_query=limit)
    finally:
        scraper.close()


# ═══════════════════════════════════════════════════════════════════════════════
# CALL COMMANDS
# ═══════════════════════════════════════════════════════════════════════════════

@cli.group()
def call():
    """Run audit calls to test business availability."""
    pass


@call.command("audit")
@click.option("--limit", "-l", default=10, help="Maximum number of calls to make")
@click.option("--all-leads", is_flag=True, help="Call all leads, not just 24/7 claimers")
@click.option("--mock", is_flag=True, help="Use mock caller (no real calls)")
@click.option("--delay", "-d", default=5, help="Seconds between calls")
def audit_calls(limit: int, all_leads: bool, mock: bool, delay: int):
    """
    Run audit calls on leads to test if they answer.
    
    Example: nightline call audit --limit 20 --mock
    """
    only_24_7 = not all_leads
    
    console.print(Panel.fit(
        f"[bold blue]📞 Audit Call Batch[/bold blue]\n"
        f"Max calls: {limit}\n"
        f"24/7 claimers only: {'No' if all_leads else 'Yes'}\n"
        f"Mode: {'MOCK (no real calls)' if mock else 'LIVE'}",
        title="Nightline Caller"
    ))
    
    if mock:
        caller = MockAuditCaller()
    else:
        try:
            caller = AuditCaller()
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            console.print("[yellow]Tip: Use --mock flag to test without Twilio credentials[/yellow]")
            return
    
    try:
        caller.run_audit_batch(
            only_24_7=only_24_7, 
            limit=limit,
            delay_between_calls=delay
        )
    finally:
        caller.close()


@call.command("single")
@click.argument("lead_id", type=int)
@click.option("--mock", is_flag=True, help="Use mock caller")
def call_single(lead_id: int, mock: bool):
    """
    Make a single audit call to a specific lead.
    
    Example: nightline call single 123
    """
    session = get_session()
    lead = session.query(Lead).filter_by(id=lead_id).first()
    
    if not lead:
        console.print(f"[red]Lead with ID {lead_id} not found.[/red]")
        return
    
    console.print(f"Calling: {lead.name} at {lead.phone_number}")
    
    if mock:
        caller = MockAuditCaller()
    else:
        caller = AuditCaller()
    
    try:
        audit = caller.make_audit_call(lead)
        console.print(f"Result: {audit.outcome.value}")
    finally:
        caller.close()


# ═══════════════════════════════════════════════════════════════════════════════
# LEADS COMMANDS
# ═══════════════════════════════════════════════════════════════════════════════

@cli.group()
def leads():
    """Manage and view leads."""
    pass


@leads.command("list")
@click.option("--status", "-s", type=click.Choice(["new", "qualified", "disqualified", "all"]), default="all")
@click.option("--city", "-c", help="Filter by city")
@click.option("--industry", "-i", type=click.Choice(INDUSTRY_KEYS + ["all"], case_sensitive=False), default="all", help="Filter by industry")
@click.option("--source", type=click.Choice(["lsa", "google_maps", "all"]), default="all", help="Filter by source")
@click.option("--sponsored", is_flag=True, help="Only show LSA sponsored leads")
@click.option("--24-7", "claims_24_7", is_flag=True, help="Only show 24/7 claimers")
@click.option("--limit", "-l", default=50, help="Maximum leads to show")
def list_leads(status: str, city: str, industry: str, source: str, sponsored: bool, claims_24_7: bool, limit: int):
    """
    List leads in the database.
    
    Examples:
        nightline leads list --industry pi --sponsored
        nightline leads list --city "Los Angeles" --status new
        nightline leads list --source lsa --limit 100
    """
    session = get_session()
    query = session.query(Lead)
    
    if status != "all":
        status_map = {
            "new": LeadStatus.NEW,
            "qualified": LeadStatus.QUALIFIED,
            "disqualified": LeadStatus.DISQUALIFIED,
        }
        query = query.filter(Lead.status == status_map[status])
    
    if city:
        query = query.filter(Lead.city.ilike(f"%{city}%"))
    
    if industry != "all":
        query = query.filter(Lead.industry == industry)
    
    if source != "all":
        query = query.filter(Lead.source_type == source)
    
    if sponsored:
        query = query.filter(Lead.is_sponsored == True)
    
    if claims_24_7:
        query = query.filter(Lead.claims_24_7 == True)
    
    leads_result = query.limit(limit).all()
    
    if not leads_result:
        console.print("[yellow]No leads found matching criteria.[/yellow]")
        return
    
    table = Table(title=f"Leads ({len(leads_result)} shown)")
    table.add_column("ID", style="dim")
    table.add_column("Business Name", style="cyan")
    table.add_column("Phone", style="green")
    table.add_column("City", style="blue")
    table.add_column("Industry", style="yellow")
    table.add_column("Source", style="dim")
    table.add_column("Status", style="magenta")
    
    for lead in leads_result:
        source_label = "LSA" if lead.source_type == "lsa" else "Maps"
        if lead.is_sponsored:
            source_label += " *"
        
        table.add_row(
            str(lead.id),
            lead.name[:35] + "..." if len(lead.name) > 35 else lead.name,
            lead.phone_number or "N/A",
            lead.city or "Unknown",
            (lead.industry or "hvac").upper(),
            source_label,
            lead.status.value.upper(),
        )
    
    console.print(table)
    console.print("[dim]* = Sponsored (LSA Ad)[/dim]")


@leads.command("qualified")
@click.option("--export", "-e", type=click.Path(), help="Export to CSV file")
def qualified_leads(export: str):
    """
    Show all qualified leads (didn't answer - ready for sales!).
    
    Example: nightline leads qualified --export leads.csv
    """
    session = get_session()
    leads = session.query(Lead).filter(Lead.status == LeadStatus.QUALIFIED).all()
    
    if not leads:
        console.print("[yellow]No qualified leads yet. Run some audit calls first![/yellow]")
        return
    
    console.print(Panel.fit(
        f"[bold yellow]💰 {len(leads)} Qualified Leads[/bold yellow]\n"
        "These businesses claim 24/7 service but didn't answer!",
        title="Sales Opportunities"
    ))
    
    table = Table()
    table.add_column("Business", style="cyan")
    table.add_column("Phone", style="green")
    table.add_column("Location", style="blue")
    table.add_column("Rating", style="yellow")
    table.add_column("Keywords", style="dim")
    
    for lead in leads:
        table.add_row(
            lead.name,
            lead.phone_number,
            f"{lead.city}, {lead.state}" if lead.city else lead.full_address[:40] if lead.full_address else "Unknown",
            f"⭐ {lead.rating}" if lead.rating else "N/A",
            lead.availability_keywords_found[:30] if lead.availability_keywords_found else ""
        )
    
    console.print(table)
    
    if export:
        import csv
        with open(export, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Name", "Phone", "City", "State", "Address", "Rating", "Reviews", "Website", "Keywords"])
            for lead in leads:
                writer.writerow([
                    lead.name,
                    lead.phone_number,
                    lead.city,
                    lead.state,
                    lead.full_address,
                    lead.rating,
                    lead.review_count,
                    lead.website,
                    lead.availability_keywords_found
                ])
        console.print(f"\n[green]✓ Exported to {export}[/green]")


@leads.command("stats")
def lead_stats():
    """Show overall statistics with industry breakdown."""
    from sqlalchemy import func
    
    session = get_session()
    
    total = session.query(Lead).count()
    new = session.query(Lead).filter(Lead.status == LeadStatus.NEW).count()
    qualified = session.query(Lead).filter(Lead.status == LeadStatus.QUALIFIED).count()
    disqualified = session.query(Lead).filter(Lead.status == LeadStatus.DISQUALIFIED).count()
    claims_24_7 = session.query(Lead).filter(Lead.claims_24_7 == True).count()
    lsa_count = session.query(Lead).filter(Lead.source_type == "lsa").count()
    sponsored_count = session.query(Lead).filter(Lead.is_sponsored == True).count()
    
    total_calls = session.query(CallAudit).count()
    answered = session.query(CallAudit).filter(CallAudit.outcome == CallOutcome.ANSWERED).count()
    voicemail = session.query(CallAudit).filter(CallAudit.outcome == CallOutcome.VOICEMAIL).count()
    no_answer = session.query(CallAudit).filter(CallAudit.outcome == CallOutcome.NO_ANSWER).count()
    
    console.print(Panel.fit(
        "[bold blue]Nightline Statistics[/bold blue]",
        title="Dashboard"
    ))
    
    # Overall leads table
    leads_table = Table(title="Leads Overview")
    leads_table.add_column("Metric", style="cyan")
    leads_table.add_column("Count", style="magenta")
    
    leads_table.add_row("Total Leads", str(total))
    leads_table.add_row("From LSA (sponsored)", str(lsa_count))
    leads_table.add_row("Claiming 24/7", str(claims_24_7))
    leads_table.add_row("New (not called)", str(new))
    leads_table.add_row("[green]Qualified (sales ready)[/green]", f"[green]{qualified}[/green]")
    leads_table.add_row("Disqualified (answered)", str(disqualified))
    
    console.print(leads_table)
    
    # Industry breakdown
    industry_counts = (
        session.query(Lead.industry, func.count(Lead.id))
        .group_by(Lead.industry)
        .all()
    )
    
    if industry_counts:
        ind_table = Table(title="By Industry")
        ind_table.add_column("Industry", style="cyan")
        ind_table.add_column("Leads", style="magenta")
        
        for industry_key, count in sorted(industry_counts, key=lambda x: x[1], reverse=True):
            label = INDUSTRIES.get(industry_key, {}).get("name", industry_key or "Unknown")
            ind_table.add_row(label, str(count))
        
        console.print(ind_table)
    
    if total_calls > 0:
        calls_table = Table(title="Audit Calls")
        calls_table.add_column("Outcome", style="cyan")
        calls_table.add_column("Count", style="magenta")
        calls_table.add_column("Rate", style="green")
        
        calls_table.add_row("Total Calls", str(total_calls), "")
        calls_table.add_row("Answered", str(answered), f"{answered/total_calls*100:.1f}%")
        calls_table.add_row("Voicemail", str(voicemail), f"{voicemail/total_calls*100:.1f}%")
        calls_table.add_row("No Answer", str(no_answer), f"{no_answer/total_calls*100:.1f}%")
        
        console.print(calls_table)
        
        success_rate = (voicemail + no_answer) / total_calls * 100 if total_calls else 0
        console.print(f"\n[bold yellow]Qualification Rate: {success_rate:.1f}%[/bold yellow]")


# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE COMMANDS
# ═══════════════════════════════════════════════════════════════════════════════

@cli.group()
def db():
    """Database management commands."""
    pass


@db.command("init")
def init_database():
    """Initialize the database (create tables)."""
    init_db()
    console.print("[green]✓ Database initialized successfully![/green]")


@db.command("reset")
@click.confirmation_option(prompt="Are you sure you want to delete all data?")
def reset_database():
    """Reset the database (delete all data)."""
    from .database import Base, engine
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    console.print("[green]✓ Database reset successfully![/green]")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()


"""
Web dashboard for Nightline lead management.
"""
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Request, Query, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import json

from .database import (
    init_db, get_session, 
    Lead, CallAudit, ScrapeRun,
    LeadStatus, CallOutcome
)
from .scraper import HVACLeadScraper
from .caller import AuditCaller, MockAuditCaller

# Initialize FastAPI
app = FastAPI(
    title="Nightline Dashboard",
    description="AI-Powered Lead Generation System",
    version="1.0.0"
)

# Initialize database on startup
@app.on_event("startup")
async def startup():
    init_db()


# ═══════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class ScrapeRequest(BaseModel):
    city: str
    state: str
    limit: int = 50


class CallBatchRequest(BaseModel):
    limit: int = 10
    only_24_7: bool = True
    mock: bool = True


class LeadResponse(BaseModel):
    id: int
    name: str
    phone_number: Optional[str]
    city: Optional[str]
    state: Optional[str]
    rating: Optional[float]
    review_count: Optional[int]
    claims_24_7: bool
    status: str
    website: Optional[str]
    full_address: Optional[str]
    availability_keywords: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class StatsResponse(BaseModel):
    total_leads: int
    new_leads: int
    qualified_leads: int
    disqualified_leads: int
    claims_24_7: int
    total_calls: int
    answered: int
    voicemail: int
    no_answer: int
    qualification_rate: float


# ═══════════════════════════════════════════════════════════════════════════════
# HTML DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nightline Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-tertiary: #1a1a24;
            --accent-primary: #6366f1;
            --accent-secondary: #818cf8;
            --accent-glow: rgba(99, 102, 241, 0.3);
            --success: #22c55e;
            --warning: #f59e0b;
            --danger: #ef4444;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --border: #2e2e3a;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Space Grotesk', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            background-image: 
                radial-gradient(ellipse at top, rgba(99, 102, 241, 0.1) 0%, transparent 50%),
                radial-gradient(ellipse at bottom right, rgba(139, 92, 246, 0.05) 0%, transparent 50%);
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }
        
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 3rem;
            padding-bottom: 2rem;
            border-bottom: 1px solid var(--border);
        }
        
        .logo {
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        
        .logo-icon {
            width: 48px;
            height: 48px;
            background: linear-gradient(135deg, var(--accent-primary), #8b5cf6);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            box-shadow: 0 4px 20px var(--accent-glow);
        }
        
        h1 {
            font-size: 1.75rem;
            font-weight: 700;
            letter-spacing: -0.025em;
        }
        
        h1 span {
            color: var(--accent-secondary);
        }
        
        .subtitle {
            color: var(--text-muted);
            font-size: 0.875rem;
            margin-top: 0.25rem;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.5rem;
            margin-bottom: 3rem;
        }
        
        .stat-card {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1.5rem;
            transition: all 0.3s ease;
        }
        
        .stat-card:hover {
            border-color: var(--accent-primary);
            box-shadow: 0 4px 30px var(--accent-glow);
            transform: translateY(-2px);
        }
        
        .stat-card.highlight {
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(139, 92, 246, 0.1));
            border-color: var(--accent-primary);
        }
        
        .stat-label {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
        }
        
        .stat-value {
            font-family: 'JetBrains Mono', monospace;
            font-size: 2rem;
            font-weight: 700;
            color: var(--text-primary);
        }
        
        .stat-value.success { color: var(--success); }
        .stat-value.warning { color: var(--warning); }
        .stat-value.danger { color: var(--danger); }
        
        .section {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 16px;
            margin-bottom: 2rem;
            overflow: hidden;
        }
        
        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1.5rem;
            border-bottom: 1px solid var(--border);
        }
        
        .section-title {
            font-size: 1.125rem;
            font-weight: 600;
        }
        
        .actions {
            display: flex;
            gap: 0.75rem;
        }
        
        .btn {
            font-family: 'Space Grotesk', sans-serif;
            padding: 0.75rem 1.5rem;
            border-radius: 8px;
            border: none;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.875rem;
        }
        
        .btn-primary {
            background: linear-gradient(135deg, var(--accent-primary), #8b5cf6);
            color: white;
        }
        
        .btn-primary:hover {
            box-shadow: 0 4px 20px var(--accent-glow);
            transform: translateY(-1px);
        }
        
        .btn-secondary {
            background: var(--bg-tertiary);
            color: var(--text-primary);
            border: 1px solid var(--border);
        }
        
        .btn-secondary:hover {
            border-color: var(--accent-primary);
        }
        
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        th, td {
            padding: 1rem 1.5rem;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }
        
        th {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--text-muted);
            font-weight: 600;
        }
        
        tr:hover td {
            background: var(--bg-tertiary);
        }
        
        .badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }
        
        .badge-success { background: rgba(34, 197, 94, 0.2); color: var(--success); }
        .badge-warning { background: rgba(245, 158, 11, 0.2); color: var(--warning); }
        .badge-danger { background: rgba(239, 68, 68, 0.2); color: var(--danger); }
        .badge-info { background: rgba(99, 102, 241, 0.2); color: var(--accent-secondary); }
        
        .form-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            padding: 1.5rem;
        }
        
        .form-group {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }
        
        .form-group label {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--text-muted);
        }
        
        .form-group input, .form-group select {
            padding: 0.75rem 1rem;
            border-radius: 8px;
            border: 1px solid var(--border);
            background: var(--bg-tertiary);
            color: var(--text-primary);
            font-family: inherit;
            font-size: 0.875rem;
        }
        
        .form-group input:focus, .form-group select:focus {
            outline: none;
            border-color: var(--accent-primary);
            box-shadow: 0 0 0 3px var(--accent-glow);
        }
        
        .loading {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid transparent;
            border-top-color: currentColor;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .empty-state {
            padding: 4rem 2rem;
            text-align: center;
            color: var(--text-muted);
        }
        
        .empty-state p {
            margin-bottom: 1rem;
        }
        
        .toast {
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            padding: 1rem 1.5rem;
            border-radius: 8px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
            transform: translateY(100px);
            opacity: 0;
            transition: all 0.3s ease;
        }
        
        .toast.show {
            transform: translateY(0);
            opacity: 1;
        }
        
        .toast.success { border-color: var(--success); }
        .toast.error { border-color: var(--danger); }
        
        .phone-link {
            color: var(--accent-secondary);
            text-decoration: none;
        }
        
        .phone-link:hover {
            text-decoration: underline;
        }
        
        @media (max-width: 768px) {
            .container { padding: 1rem; }
            .stats-grid { grid-template-columns: repeat(2, 1fr); }
            .section-header { flex-direction: column; gap: 1rem; }
            .actions { width: 100%; }
            .btn { flex: 1; justify-content: center; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo">
                <div class="logo-icon">🌙</div>
                <div>
                    <h1>Night<span>line</span></h1>
                    <p class="subtitle">Lead Generation Dashboard</p>
                </div>
            </div>
            <div class="actions">
                <button class="btn btn-secondary" onclick="refreshStats()">↻ Refresh</button>
            </div>
        </header>
        
        <div class="stats-grid" id="stats-grid">
            <!-- Stats loaded via JS -->
        </div>
        
        <!-- Scrape Section -->
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">🔍 Scrape HVAC Leads</h2>
            </div>
            <div class="form-grid">
                <div class="form-group">
                    <label>City</label>
                    <input type="text" id="scrape-city" placeholder="Denver">
                </div>
                <div class="form-group">
                    <label>State</label>
                    <input type="text" id="scrape-state" placeholder="CO">
                </div>
                <div class="form-group">
                    <label>Limit per Query</label>
                    <input type="number" id="scrape-limit" value="50" min="1" max="200">
                </div>
                <div class="form-group" style="justify-content: flex-end;">
                    <button class="btn btn-primary" onclick="startScrape()" id="scrape-btn">
                        Start Scraping
                    </button>
                </div>
            </div>
        </div>
        
        <!-- Call Audit Section -->
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">📞 Audit Calls</h2>
            </div>
            <div class="form-grid">
                <div class="form-group">
                    <label>Max Calls</label>
                    <input type="number" id="call-limit" value="10" min="1" max="100">
                </div>
                <div class="form-group">
                    <label>Target</label>
                    <select id="call-target">
                        <option value="24-7">24/7 Claimers Only</option>
                        <option value="all">All Leads</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Mode</label>
                    <select id="call-mode">
                        <option value="mock">Mock (Testing)</option>
                        <option value="live">Live Calls</option>
                    </select>
                </div>
                <div class="form-group" style="justify-content: flex-end;">
                    <button class="btn btn-primary" onclick="startCalls()" id="call-btn">
                        Run Audit Batch
                    </button>
                </div>
            </div>
        </div>
        
        <!-- Qualified Leads Section -->
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">💰 Qualified Leads (Ready for Sales)</h2>
                <div class="actions">
                    <button class="btn btn-secondary" onclick="exportLeads()">Export CSV</button>
                </div>
            </div>
            <div id="qualified-leads-container">
                <div class="empty-state">
                    <p>Loading leads...</p>
                </div>
            </div>
        </div>
        
        <!-- All Leads Section -->
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">📋 All Leads</h2>
                <div class="actions">
                    <select id="status-filter" onchange="loadLeads()">
                        <option value="all">All Statuses</option>
                        <option value="new">New</option>
                        <option value="qualified">Qualified</option>
                        <option value="disqualified">Disqualified</option>
                    </select>
                </div>
            </div>
            <div id="all-leads-container">
                <div class="empty-state">
                    <p>Loading leads...</p>
                </div>
            </div>
        </div>
    </div>
    
    <div class="toast" id="toast"></div>
    
    <script>
        // API Functions
        async function fetchStats() {
            const res = await fetch('/api/stats');
            return res.json();
        }
        
        async function fetchLeads(status = 'all', limit = 100) {
            const url = status === 'all' 
                ? `/api/leads?limit=${limit}` 
                : `/api/leads?status=${status}&limit=${limit}`;
            const res = await fetch(url);
            return res.json();
        }
        
        async function fetchQualifiedLeads() {
            const res = await fetch('/api/leads/qualified');
            return res.json();
        }
        
        // UI Rendering
        function renderStats(stats) {
            const grid = document.getElementById('stats-grid');
            grid.innerHTML = `
                <div class="stat-card">
                    <div class="stat-label">Total Leads</div>
                    <div class="stat-value">${stats.total_leads}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">24/7 Claimers</div>
                    <div class="stat-value">${stats.claims_24_7}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">New (Uncalled)</div>
                    <div class="stat-value">${stats.new_leads}</div>
                </div>
                <div class="stat-card highlight">
                    <div class="stat-label">Qualified Leads</div>
                    <div class="stat-value success">${stats.qualified_leads}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Total Calls</div>
                    <div class="stat-value">${stats.total_calls}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Qualification Rate</div>
                    <div class="stat-value warning">${stats.qualification_rate.toFixed(1)}%</div>
                </div>
            `;
        }
        
        function renderLeadsTable(leads, containerId) {
            const container = document.getElementById(containerId);
            
            if (!leads.length) {
                container.innerHTML = `
                    <div class="empty-state">
                        <p>No leads found</p>
                        <button class="btn btn-primary" onclick="document.getElementById('scrape-city').focus()">
                            Start Scraping
                        </button>
                    </div>
                `;
                return;
            }
            
            const statusBadge = (status) => {
                const classes = {
                    'new': 'badge-info',
                    'qualified': 'badge-success',
                    'disqualified': 'badge-danger',
                    'called': 'badge-warning'
                };
                return `<span class="badge ${classes[status] || 'badge-info'}">${status}</span>`;
            };
            
            container.innerHTML = `
                <table>
                    <thead>
                        <tr>
                            <th>Business</th>
                            <th>Phone</th>
                            <th>Location</th>
                            <th>Rating</th>
                            <th>24/7</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${leads.map(lead => `
                            <tr>
                                <td>
                                    <strong>${lead.name}</strong>
                                    ${lead.website ? `<br><a href="${lead.website}" target="_blank" class="phone-link" style="font-size: 0.75rem;">Website ↗</a>` : ''}
                                </td>
                                <td>
                                    <a href="tel:${lead.phone_number}" class="phone-link">${lead.phone_number || 'N/A'}</a>
                                </td>
                                <td>${lead.city ? `${lead.city}, ${lead.state}` : (lead.full_address || 'Unknown').slice(0, 30)}</td>
                                <td>${lead.rating ? `⭐ ${lead.rating}` : 'N/A'}</td>
                                <td>${lead.claims_24_7 ? '✓' : ''}</td>
                                <td>${statusBadge(lead.status)}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        }
        
        // Actions
        async function startScrape() {
            const city = document.getElementById('scrape-city').value;
            const state = document.getElementById('scrape-state').value;
            const limit = parseInt(document.getElementById('scrape-limit').value);
            
            if (!city || !state) {
                showToast('Please enter city and state', 'error');
                return;
            }
            
            const btn = document.getElementById('scrape-btn');
            btn.disabled = true;
            btn.innerHTML = '<span class="loading"></span> Scraping...';
            
            try {
                const res = await fetch('/api/scrape', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ city, state, limit })
                });
                const data = await res.json();
                
                if (data.success) {
                    showToast(`Found ${data.stats.new_leads} new leads!`, 'success');
                    refreshAll();
                } else {
                    showToast(data.error || 'Scraping failed', 'error');
                }
            } catch (e) {
                showToast('Error: ' + e.message, 'error');
            } finally {
                btn.disabled = false;
                btn.innerHTML = 'Start Scraping';
            }
        }
        
        async function startCalls() {
            const limit = parseInt(document.getElementById('call-limit').value);
            const only_24_7 = document.getElementById('call-target').value === '24-7';
            const mock = document.getElementById('call-mode').value === 'mock';
            
            const btn = document.getElementById('call-btn');
            btn.disabled = true;
            btn.innerHTML = '<span class="loading"></span> Calling...';
            
            try {
                const res = await fetch('/api/calls/batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ limit, only_24_7, mock })
                });
                const data = await res.json();
                
                if (data.success) {
                    const qualified = data.stats.voicemail + data.stats.no_answer;
                    showToast(`Completed! ${qualified} new qualified leads`, 'success');
                    refreshAll();
                } else {
                    showToast(data.error || 'Calls failed', 'error');
                }
            } catch (e) {
                showToast('Error: ' + e.message, 'error');
            } finally {
                btn.disabled = false;
                btn.innerHTML = 'Run Audit Batch';
            }
        }
        
        async function exportLeads() {
            window.open('/api/leads/export', '_blank');
        }
        
        // Utilities
        function showToast(message, type = 'info') {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast show ' + type;
            setTimeout(() => toast.classList.remove('show'), 3000);
        }
        
        async function refreshStats() {
            const stats = await fetchStats();
            renderStats(stats);
        }
        
        async function loadLeads() {
            const status = document.getElementById('status-filter').value;
            const leads = await fetchLeads(status);
            renderLeadsTable(leads, 'all-leads-container');
        }
        
        async function loadQualifiedLeads() {
            const leads = await fetchQualifiedLeads();
            renderLeadsTable(leads, 'qualified-leads-container');
        }
        
        async function refreshAll() {
            await Promise.all([
                refreshStats(),
                loadLeads(),
                loadQualifiedLeads()
            ]);
        }
        
        // Initial load
        refreshAll();
    </script>
</body>
</html>
'''


# ═══════════════════════════════════════════════════════════════════════════════
# API ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the main dashboard."""
    return DASHBOARD_HTML


@app.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    """Get overall statistics."""
    session = get_session()
    try:
        total = session.query(Lead).count()
        new = session.query(Lead).filter(Lead.status == LeadStatus.NEW).count()
        qualified = session.query(Lead).filter(Lead.status == LeadStatus.QUALIFIED).count()
        disqualified = session.query(Lead).filter(Lead.status == LeadStatus.DISQUALIFIED).count()
        claims_24_7 = session.query(Lead).filter(Lead.claims_24_7 == True).count()
        
        total_calls = session.query(CallAudit).count()
        answered = session.query(CallAudit).filter(CallAudit.outcome == CallOutcome.ANSWERED).count()
        voicemail = session.query(CallAudit).filter(CallAudit.outcome == CallOutcome.VOICEMAIL).count()
        no_answer = session.query(CallAudit).filter(CallAudit.outcome == CallOutcome.NO_ANSWER).count()
        
        qualification_rate = ((voicemail + no_answer) / total_calls * 100) if total_calls > 0 else 0
        
        return StatsResponse(
            total_leads=total,
            new_leads=new,
            qualified_leads=qualified,
            disqualified_leads=disqualified,
            claims_24_7=claims_24_7,
            total_calls=total_calls,
            answered=answered,
            voicemail=voicemail,
            no_answer=no_answer,
            qualification_rate=qualification_rate
        )
    finally:
        session.close()


@app.get("/api/leads")
async def get_leads(
    status: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    claims_24_7: Optional[bool] = Query(None),
    limit: int = Query(100)
):
    """Get leads with optional filtering."""
    session = get_session()
    try:
        query = session.query(Lead)
        
        if status and status != "all":
            status_map = {
                "new": LeadStatus.NEW,
                "qualified": LeadStatus.QUALIFIED,
                "disqualified": LeadStatus.DISQUALIFIED,
                "called": LeadStatus.CALLED,
            }
            if status in status_map:
                query = query.filter(Lead.status == status_map[status])
        
        if city:
            query = query.filter(Lead.city.ilike(f"%{city}%"))
        
        if claims_24_7:
            query = query.filter(Lead.claims_24_7 == True)
        
        leads = query.order_by(Lead.created_at.desc()).limit(limit).all()
        
        return [
            {
                "id": lead.id,
                "name": lead.name,
                "phone_number": lead.phone_number,
                "city": lead.city,
                "state": lead.state,
                "rating": lead.rating,
                "review_count": lead.review_count,
                "claims_24_7": lead.claims_24_7,
                "status": lead.status.value,
                "website": lead.website,
                "full_address": lead.full_address,
                "availability_keywords": lead.availability_keywords_found,
                "created_at": lead.created_at.isoformat() if lead.created_at else None
            }
            for lead in leads
        ]
    finally:
        session.close()


@app.get("/api/leads/qualified")
async def get_qualified_leads():
    """Get all qualified leads (didn't answer)."""
    session = get_session()
    try:
        leads = session.query(Lead).filter(
            Lead.status == LeadStatus.QUALIFIED
        ).order_by(Lead.created_at.desc()).all()
        
        return [
            {
                "id": lead.id,
                "name": lead.name,
                "phone_number": lead.phone_number,
                "city": lead.city,
                "state": lead.state,
                "rating": lead.rating,
                "review_count": lead.review_count,
                "claims_24_7": lead.claims_24_7,
                "status": lead.status.value,
                "website": lead.website,
                "full_address": lead.full_address,
                "availability_keywords": lead.availability_keywords_found,
                "created_at": lead.created_at.isoformat() if lead.created_at else None
            }
            for lead in leads
        ]
    finally:
        session.close()


@app.get("/api/leads/export")
async def export_leads_csv():
    """Export qualified leads as CSV."""
    import io
    import csv
    from fastapi.responses import StreamingResponse
    
    session = get_session()
    try:
        leads = session.query(Lead).filter(
            Lead.status == LeadStatus.QUALIFIED
        ).all()
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Name", "Phone", "City", "State", "Address", "Rating", "Reviews", "Website", "24/7 Keywords"])
        
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
        
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=qualified_leads.csv"}
        )
    finally:
        session.close()


@app.post("/api/scrape")
async def scrape_city(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """Start a scrape job for a city."""
    try:
        scraper = HVACLeadScraper()
        stats = scraper.scrape_city(
            request.city, 
            request.state, 
            limit_per_query=request.limit
        )
        scraper.close()
        
        return {"success": True, "stats": stats}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.post("/api/calls/batch")
async def run_call_batch(request: CallBatchRequest):
    """Run a batch of audit calls."""
    try:
        if request.mock:
            caller = MockAuditCaller()
        else:
            caller = AuditCaller()
        
        stats = caller.run_audit_batch(
            only_24_7=request.only_24_7,
            limit=request.limit
        )
        caller.close()
        
        return {"success": True, "stats": stats}
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(e)}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.get("/api/lead/{lead_id}")
async def get_lead(lead_id: int):
    """Get a specific lead with call history."""
    session = get_session()
    try:
        lead = session.query(Lead).filter_by(id=lead_id).first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        
        calls = session.query(CallAudit).filter_by(lead_id=lead_id).order_by(
            CallAudit.call_initiated_at.desc()
        ).all()
        
        return {
            "lead": {
                "id": lead.id,
                "name": lead.name,
                "phone_number": lead.phone_number,
                "city": lead.city,
                "state": lead.state,
                "full_address": lead.full_address,
                "rating": lead.rating,
                "review_count": lead.review_count,
                "claims_24_7": lead.claims_24_7,
                "availability_keywords": lead.availability_keywords_found,
                "status": lead.status.value,
                "website": lead.website,
                "hours": json.loads(lead.hours_json) if lead.hours_json else None
            },
            "calls": [
                {
                    "id": call.id,
                    "initiated_at": call.call_initiated_at.isoformat(),
                    "outcome": call.outcome.value,
                    "answered_by": call.answered_by,
                    "duration": call.call_duration_seconds,
                    "time_of_day": call.time_of_day,
                    "day_of_week": call.day_of_week,
                    "is_business_hours": call.is_business_hours
                }
                for call in calls
            ]
        }
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════════════
# TWILIO WEBHOOK (for async call status updates)
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/twilio/callback")
async def twilio_callback(request: Request):
    """
    Webhook endpoint for Twilio call status updates.
    In production, use this instead of polling for call completion.
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    call_status = form_data.get("CallStatus")
    answered_by = form_data.get("AnsweredBy")
    
    if call_sid:
        session = get_session()
        try:
            audit = session.query(CallAudit).filter_by(twilio_call_sid=call_sid).first()
            if audit:
                audit.call_ended_at = datetime.utcnow()
                
                if call_status == "completed":
                    if answered_by == "human":
                        audit.outcome = CallOutcome.ANSWERED
                        audit.answered_by = "human"
                    elif answered_by and "machine" in answered_by:
                        audit.outcome = CallOutcome.VOICEMAIL
                        audit.answered_by = "machine"
                elif call_status == "no-answer":
                    audit.outcome = CallOutcome.NO_ANSWER
                elif call_status == "busy":
                    audit.outcome = CallOutcome.BUSY
                
                session.commit()
        finally:
            session.close()
    
    return {"status": "received"}


def run_dashboard(host: str = "0.0.0.0", port: int = 8000):
    """Run the dashboard server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_dashboard()


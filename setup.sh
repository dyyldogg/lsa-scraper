#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Nightline / LSA Scraper - One-Command Setup
# ═══════════════════════════════════════════════════════════════════════════════
# Usage: chmod +x setup.sh && ./setup.sh
# ═══════════════════════════════════════════════════════════════════════════════

set -e

echo "═══════════════════════════════════════════════════════════"
echo "  Nightline / LSA Scraper - Setup"
echo "═══════════════════════════════════════════════════════════"

# 1. Check Python
echo ""
echo "[1/5] Checking Python..."
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "  ❌ Python not found. Install Python 3.9+ first."
    exit 1
fi
echo "  ✓ Using: $($PYTHON --version)"

# 2. Install pip dependencies
echo ""
echo "[2/5] Installing Python packages..."
$PYTHON -m pip install -r requirements.txt --quiet
echo "  ✓ All packages installed"

# 3. Install Playwright + Chromium browser
echo ""
echo "[3/5] Installing Playwright browser (Chromium)..."
$PYTHON -m playwright install chromium
echo "  ✓ Chromium installed"

# 4. Create .env if it doesn't exist
echo ""
echo "[4/5] Checking .env config..."
if [ ! -f .env ]; then
    cp env.example .env
    echo "  ✓ Created .env from env.example"
    echo "  ⚠  IMPORTANT: Edit .env and add your API keys!"
else
    echo "  ✓ .env already exists"
fi

# 5. Initialize database
echo ""
echo "[5/5] Initializing database..."
$PYTHON -c "from nightline.database import init_db; init_db()"
echo "  ✓ Database ready"

# Create data directory
mkdir -p data

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✓ Setup Complete!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  NEXT STEPS:"
echo ""
echo "  1. Edit .env with your API keys (see env.example for details)"
echo ""
echo "  2. Scrape leads (no API key needed):"
echo "     $PYTHON -m nightline.cli lsa city pi 'Los Angeles' CA"
echo ""
echo "  3. Call leads (needs VAPI_API_KEY + VAPI_PHONE_ID in .env):"
echo "     $PYTHON vapi_caller.py --test"
echo ""
echo "  4. Run the dashboard:"
echo "     $PYTHON -m nightline.cli dashboard"
echo "     → Open http://localhost:8000"
echo ""
echo "═══════════════════════════════════════════════════════════"

#!/usr/bin/env python3
"""
Google LSA Sponsored Listings Scraper
Scrapes business names from Google Local Services Ads prolist page.
All listings on that page are SPONSORED (paid ads).

Uses your real Chrome browser (channel="chrome") to avoid bot detection.

Usage:
    python scrape_pi_lawyers.py --test --visible   # 3 zips, see browser
    python scrape_pi_lawyers.py                    # all 50 zips headless
    python scrape_pi_lawyers.py --service "HVAC"   # different category
"""
import asyncio, csv, re, random, argparse, sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("pip install playwright && playwright install chromium")
    sys.exit(1)

OUTPUT_DIR = Path("data")
OUTPUT_DIR.mkdir(exist_ok=True)

TARGET_LOCATIONS = [
    ("77701","Beaumont, TX"),("78401","Corpus Christi, TX"),
    ("79401","Lubbock, TX"),("79101","Amarillo, TX"),
    ("76701","Waco, TX"),("78501","McAllen, TX"),
    ("75702","Tyler, TX"),("71101","Shreveport, LA"),
    ("70801","Baton Rouge, LA"),("70601","Lake Charles, LA"),
    ("39201","Jackson, MS"),("39530","Biloxi, MS"),
    ("36602","Mobile, AL"),("36104","Montgomery, AL"),
    ("35801","Huntsville, AL"),("31401","Savannah, GA"),
    ("31201","Macon, GA"),("30901","Augusta, GA"),
    ("28301","Fayetteville, NC"),("28401","Wilmington, NC"),
    ("37402","Chattanooga, TN"),("37902","Knoxville, TN"),
    ("38103","Memphis, TN"),("72201","Little Rock, AR"),
    ("29601","Greenville, SC"),("29201","Columbia, SC"),
    ("44302","Akron, OH"),("45402","Dayton, OH"),
    ("43604","Toledo, OH"),("46802","Fort Wayne, IN"),
    ("46601","South Bend, IN"),("61101","Rockford, IL"),
    ("62701","Springfield, IL"),("52401","Cedar Rapids, IA"),
    ("67202","Wichita, KS"),("66603","Topeka, KS"),
    ("85701","Tucson, AZ"),("87101","Albuquerque, NM"),
    ("79901","El Paso, TX"),("83702","Boise, ID"),
    ("89501","Reno, NV"),("99201","Spokane, WA"),
    ("93301","Bakersfield, CA"),("93721","Fresno, CA"),
    ("95202","Stockton, CA"),("95354","Modesto, CA"),
    ("13202","Syracuse, NY"),("14604","Rochester, NY"),
    ("18503","Scranton, PA"),("16501","Erie, PA"),
]


def parse_business(text):
    """Parse business name/data from an LSA button's text."""
    if not text or len(text) < 15:
        return None
    if not re.search(r"\(\d[\d,]*\)", text):
        return None
    markers = ["years in business","year in business","Serves ","Lawyer",
               "Attorney","HVAC","Plumb","Electric","Open 24","Closed","Opens "]
    if not any(m in text for m in markers):
        return None

    nm = re.match(r"^(.+?)\s*\([\d,]+\)", text)
    if not nm:
        return None
    name = nm.group(1).strip()
    if name.lower() in ("get phone","message","share","book","get quote","clear"):
        return None

    r = {"name": name}
    rev = re.search(r"\(([\d,]+)\)", text)
    if rev:
        r["reviews"] = int(rev.group(1).replace(",",""))
    yrs = re.search(r"(\d+\+?)\s*years?\s*in\s*business", text)
    if yrs:
        r["years_in_business"] = yrs.group(1)
    r["open_24h"] = "Open 24 hours" in text
    if "Open 24 hours" in text:
        r["hours"] = "Open 24 hours"
    elif "Closed" in text:
        h = re.search(r"(Closed[^\n]{0,40})", text)
        r["hours"] = h.group(1).strip() if h else "Closed"
    else:
        r["hours"] = ""
    srv = re.search(r"Serves\s+([A-Za-z\s.]+?)(?=\s+(?:Open|Closed|Closes))", text)
    if srv:
        r["serves"] = srv.group(1).strip()
    return r


FIELDS = ["name","reviews","years_in_business","open_24h",
          "hours","serves","zip_code","location","scraped_at"]

def save_csv(biz_list, path):
    if not biz_list:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(biz_list)


async def extract_businesses(page):
    biz = []
    seen = set()
    for btn in await page.get_by_role("button").all():
        try:
            text = await btn.inner_text()
            b = parse_business(text)
            if b and b["name"] not in seen:
                seen.add(b["name"])
                biz.append(b)
        except Exception:
            pass
    return biz


async def wait_for_listings(page, timeout=8.0):
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        for btn in await page.get_by_role("button").all():
            try:
                t = await btn.inner_text()
                if "years in business" in t:
                    return True
            except Exception:
                pass
        await asyncio.sleep(0.5)
    return False


async def navigate_to_lsa(page, first_zip):
    """
    Get to the LSA prolist page like a real user:
    1. Open google.com
    2. Type the search query
    3. Find and click through to the /localservices/prolist page
    """
    # -- go to google.com --
    print("  Opening google.com ...", end=" ", flush=True)
    try:
        await page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(random.uniform(2, 3))
        # accept cookies if present
        try:
            btn = await page.query_selector('button:has-text("Accept all")')
            if btn:
                await btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass
        print("OK")
    except Exception as e:
        print("failed: " + str(e))
        return False

    # -- type in search box --
    print("  Typing search query ...", end=" ", flush=True)
    try:
        q = "personal injury lawyer near " + first_zip
        box = page.locator('textarea[name="q"], input[name="q"]').first
        await box.click()
        await asyncio.sleep(0.5)
        # type slowly like a human
        await box.type(q, delay=random.uniform(40, 90))
        await asyncio.sleep(random.uniform(0.5, 1.5))
        await box.press("Enter")
        await asyncio.sleep(random.uniform(3, 5))
        print("OK")
    except Exception as e:
        print("failed: " + str(e))
        return False

    # -- find and click the LSA prolist link --
    print("  Looking for LSA prolist link ...", end=" ", flush=True)
    try:
        for _ in range(8):
            link = await page.query_selector('a[href*="/localservices/prolist"]')
            if link:
                await link.click()
                await asyncio.sleep(random.uniform(3, 5))
                print("OK")
                return True
            await page.evaluate("window.scrollBy(0, 400)")
            await asyncio.sleep(1)

        # maybe LSA content is already inline
        body = await page.inner_text("body")
        if "Search for a service" in body:
            print("OK (inline)")
            return True

        print("not found")
        await page.screenshot(path=str(OUTPUT_DIR / "lsa_search_debug.png"))
        return False
    except Exception as e:
        print("failed: " + str(e))
        return False


async def select_service(page, category):
    """Pick a service category from the dropdown."""
    try:
        combo = page.get_by_role("combobox", name="Search for a service")
        await combo.click()
        await asyncio.sleep(1)
        await combo.fill("")
        await asyncio.sleep(1.5)
        opt = page.get_by_role("option", name=category, exact=True)
        if await opt.count() > 0:
            await opt.click()
            await asyncio.sleep(4)
            return True
        await combo.fill(category)
        await asyncio.sleep(1)
        await combo.press("Enter")
        await asyncio.sleep(4)
        return True
    except Exception as e:
        print("  select_service warning: " + str(e))
        return False


async def change_area(page, zip_code):
    """Change service area to a new zip."""
    try:
        area = page.get_by_role("combobox", name="Choose a service area")
        await area.click()
        await asyncio.sleep(0.5)
        await area.fill(zip_code)
        await asyncio.sleep(2)
        await area.press("Enter")
        await asyncio.sleep(4)
        return True
    except Exception as e:
        print(" area err: " + str(e))
        return False


async def run_scraper(service="Personal Injury Law", locations=None,
                      headless=True, output_file=None):
    if locations is None:
        locations = TARGET_LOCATIONS
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if output_file is None:
        s = service.lower().replace(" ","_")
        output_file = OUTPUT_DIR / ("lsa_" + s + "_" + ts + ".csv")
    else:
        output_file = Path(output_file)

    all_biz = []
    failed = []

    print()
    print("=" * 60)
    print("  Google LSA Sponsored Listings Scraper")
    print("  Service:   " + service)
    print("  Locations: " + str(len(locations)) + " zip codes")
    print("  Output:    " + str(output_file))
    print("  Browser:   " + ("visible" if not headless else "headless"))
    print("=" * 60)
    print()

    async with async_playwright() as pw:
        # Launch your REAL Chrome, not Playwright's Chromium
        browser = await pw.chromium.launch(
            headless=headless,
            channel="chrome",
            args=["--no-sandbox","--disable-setuid-sandbox"],
        )
        ctx = await browser.new_context(
            viewport={"width": 1366, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = await ctx.new_page()

        try:
            # Step 1 - navigate to LSA page
            first_zip = locations[0][0]
            print("[Step 1] Getting to LSA page...")
            if not await navigate_to_lsa(page, first_zip):
                print("Could not reach LSA. Screenshot saved to data/")
                await page.screenshot(path=str(OUTPUT_DIR / "lsa_nav_fail.png"))
                return []

            # Step 2 - select service category
            print()
            print("[Step 2] Selecting: " + service)
            await select_service(page, service)
            await wait_for_listings(page, timeout=8)

            # Step 3 - loop through zips
            print()
            print("[Step 3] Scraping " + str(len(locations)) + " zip codes")
            print()

            for i, (zc, loc) in enumerate(locations):
                idx = str(i+1).rjust(2)
                tot = str(len(locations))
                print("  ["+idx+"/"+tot+"] "+loc.ljust(25)+" ("+zc+")", end="  ", flush=True)

                if not await change_area(page, zc):
                    print("SKIP")
                    failed.append(zc)
                    continue

                await wait_for_listings(page, timeout=6)

                # scroll to load all
                for _ in range(2):
                    try:
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await asyncio.sleep(1.2)
                    except Exception:
                        pass

                blist = await extract_businesses(page)
                for b in blist:
                    b["zip_code"] = zc
                    b["location"] = loc
                    b["scraped_at"] = datetime.now().isoformat()

                all_biz.extend(blist)
                print(str(len(blist)).rjust(2) + " firms")

                save_csv(all_biz, output_file)

                try:
                    await page.evaluate("window.scrollTo(0, 0)")
                except Exception:
                    pass

                if i < len(locations) - 1:
                    await asyncio.sleep(random.uniform(3.0, 6.0))

        except KeyboardInterrupt:
            print("\n\nInterrupted! Saving " + str(len(all_biz)) + " results...")
        except Exception as e:
            print("\nError: " + str(e))
            import traceback; traceback.print_exc()
        finally:
            if all_biz:
                save_csv(all_biz, output_file)
            try:
                await page.screenshot(path=str(OUTPUT_DIR / "lsa_final.png"))
            except Exception:
                pass
            await browser.close()

    print()
    print("=" * 60)
    print("  SCRAPE COMPLETE")
    print("  Total listings: " + str(len(all_biz)))
    if all_biz:
        u = len(set(b["name"] for b in all_biz))
        h = len([b for b in all_biz if b.get("open_24h")])
        z = len(set(b["zip_code"] for b in all_biz))
        print("  Unique firms:   " + str(u))
        print("  Open 24 hours:  " + str(h))
        print("  Zips scraped:   " + str(z) + "/" + str(len(locations)))
    if failed:
        print("  Failed zips:    " + ", ".join(failed))
    print("  Output:         " + str(output_file))
    print("=" * 60)
    print()
    return all_biz


def main():
    p = argparse.ArgumentParser(description="Scrape Google LSA sponsored listings")
    p.add_argument("--service", default="Personal Injury Law")
    p.add_argument("--test", action="store_true", help="First 3 zips only")
    p.add_argument("--visible", action="store_true", help="Show browser")
    p.add_argument("--output", default=None)
    a = p.parse_args()

    locs = TARGET_LOCATIONS
    if a.test:
        locs = TARGET_LOCATIONS[:3]
        print("TEST MODE: 3 zip codes only\n")

    asyncio.run(run_scraper(
        service=a.service, locations=locs,
        headless=not a.visible, output_file=a.output,
    ))

if __name__ == "__main__":
    main()

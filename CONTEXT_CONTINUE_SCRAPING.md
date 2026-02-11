# Context: Personal Injury Lawyers LSA Scraping Project

## PROJECT OVERVIEW
Manually scraping sponsored listings for Personal Injury Lawyers from Google Local Services Ads (LSA) using Cursor browser automation. Goal: Identify businesses claiming "Open 24 hours" for "Proof-of-Gap" sales opportunities.

## STARTING URL
https://www.google.com/localservices/prolist?g2lbs=AIBNGdWAVaT_iFAoSl7fc4Kz6aay9cczNElI0S9cdyfltuh3VVSyts8DzHKna2qFXRcos9KkNq4Z&hl=en-US&gl=us&cs=1&ssta=1&src=1&gsas=1&sa=X&slp=IgtyZXBhaXJfaHZhYyIAQAFSBAgCIABaC1JlcGFpciBIVkFD&scp=CiV4Y2F0OnNlcnZpY2VfYXJlYV9idXNpbmVzc19odmFjOmVuLVVTElUIEgkd-yYiBsnCgBEANoyI7ldk8xoSCR37JiIGycKAEQA2jIjuV2TzIhU5MDAwMSBMb3MgQW5nZWxlcywgQ0AqFA0uEzwUFVQqgrkd22BCFCUqSoe5KgRIdmFjShUKEwjsyv7L8L6SAxU9IUQIHRytDX1aC3JlcGFpcl9odmFjIAA%3D&q=%20near%2090001%20Los%20Angeles%2C%20CA

IMPORTANT: Start at this exact URL. Change service from "Repair HVAC" to "Personal Injury Law" first.

## DATA STORAGE
CSV File: /Users/dylanrochex/Projects/HVAC_leads_googleads/data/pi_lawyers_lsa_scrape.csv
Format: name,reviews,years_in_business,open_24h,hours,serves,zip_code,location,scraped_at

## WORKFLOW (Per Zip Code)
1. Click "Choose a service area" combobox
2. Clear field (browser_fill with empty string if needed)
3. Type location slowly (browser_type with slowly=true, e.g., "Jackson MS")
4. Click correct suggestion from dropdown
5. WAIT 6 seconds (browser_wait_for time=6)
6. Take snapshot (browser_snapshot compact=true)
7. Extract 20 business listings from button elements
8. Save to CSV using shell: cat >> file.csv << 'ENDOFFILE' ... ENDOFFILE

## PARSING
- name: Full firm name
- reviews: Number from parentheses "(1,010)" -> "1010"
- years_in_business: "X+ years" -> "X+"
- open_24h: True if "Open 24 hours", False otherwise
- hours: Full hours text
- serves: City from "Serves [City]"
- zip_code: Standard zip for city
- location: "City, State"
- scraped_at: YYYY-MM-DD

## COMPLETED (ZIPs 1-18)
1. 90001 Los Angeles CA
2. 77701 Beaumont TX
3. 78401 Corpus Christi TX
4. 79401 Lubbock TX
5. 79101 Amarillo TX
6. 76701 Waco TX
7. 78501 McAllen TX
8. 75702 Tyler TX
9. 71101 Shreveport LA
10. 70801 Baton Rouge LA
11. 70601 Lake Charles LA
12. 39201 Jackson MS
13. 39530 Biloxi MS
14. 36101 Montgomery AL
15. 35201 Birmingham AL
16. 36601 Mobile AL
17. 30301 Atlanta GA
18. 31401 Savannah GA

Total: 360 firm entries

## KEY FINDINGS
- 95%+ claim "Open 24 hours"
- Proof-of-Gap: Oakmont Law (LA), Burnham Law (Shreveport), Hall Law (Shreveport/Baton Rouge), Gulf South (Biloxi), Boteler Richardson (Mobile), Council & Associates (Atlanta)
- Major players: Morgan & Morgan, Morris Bart, Alexander Shunnarah, Law Tigers, Monge & Associates

## TO CONTINUE
Read CSV, ask user for ZIP 19, follow workflow above.

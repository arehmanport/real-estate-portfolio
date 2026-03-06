"""
Homes.com property listing scraper.
Run standalone: python scraper.py
"""

import csv
import os
import time

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CSV_PATH = os.path.join(DATA_DIR, "properties.csv")

FIELDNAMES = [
    "id", "price", "address", "city", "state", "zip",
    "bedrooms", "bathrooms", "sqft",
    "description", "listing_url", "image_url",
]


def scrape_homes(city="Austin", state="TX", max_pages=5):
    """Scrape property listings from Homes.com for a given city/state."""
    os.makedirs(DATA_DIR, exist_ok=True)
    listings = []

    for page in range(1, max_pages + 1):
        slug = f"{city}-{state}".replace(" ", "-")
        url = f"https://www.homes.com/{slug}/homes-for-sale/p{page}/"
        print(f"Scraping page {page}: {url}")

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  Request failed: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select('[class*="placard-container"], [class*="property-card"], [class*="listing-card"], li[class*="placard"]')

        if not cards:
            cards = soup.select("div.for-sale-content-container div, ul.placard-list li, div[data-url]")

        if not cards:
            print(f"  No listing cards found on page {page}. HTML snippet:")
            print(f"  {str(soup)[:500]}")
            break

        for card in cards:
            listing = parse_card(card, city, state)
            if listing and listing.get("address"):
                listings.append(listing)

        print(f"  Found {len(cards)} cards, {len(listings)} total listings so far")
        time.sleep(2)

    if listings:
        write_csv(listings)
        print(f"\nSaved {len(listings)} listings to {CSV_PATH}")
    else:
        print("\nNo listings scraped. Generating sample data instead...")
        generate_sample_data()

    return listings


def parse_card(card, default_city, default_state):
    """Extract listing data from a single property card element."""
    listing = {field: "" for field in FIELDNAMES}
    listing["city"] = default_city
    listing["state"] = default_state

    # Price
    price_el = card.select_one('[class*="price"], .price, span[data-label="price"]')
    if price_el:
        price_text = price_el.get_text(strip=True).replace(",", "").replace("$", "")
        digits = "".join(c for c in price_text if c.isdigit())
        if digits:
            listing["price"] = digits

    # Address
    addr_el = card.select_one('[class*="address"], .address, .street-address, a[class*="address"]')
    if addr_el:
        listing["address"] = addr_el.get_text(strip=True)

    # Beds / Baths / Sqft
    detail_els = card.select('[class*="bed"], [class*="bath"], [class*="sqft"], [class*="detail"], li')
    detail_text = " ".join(el.get_text(strip=True) for el in detail_els).lower()

    import re
    bed_match = re.search(r"(\d+)\s*(?:bd|bed|br)", detail_text)
    bath_match = re.search(r"(\d+\.?\d*)\s*(?:ba|bath)", detail_text)
    sqft_match = re.search(r"([\d,]+)\s*(?:sq\s*ft|sqft)", detail_text)

    if bed_match:
        listing["bedrooms"] = bed_match.group(1)
    if bath_match:
        listing["bathrooms"] = bath_match.group(1)
    if sqft_match:
        listing["sqft"] = sqft_match.group(1).replace(",", "")

    # Listing URL
    link_el = card.select_one("a[href]")
    if link_el:
        href = link_el["href"]
        if href.startswith("/"):
            href = "https://www.homes.com" + href
        listing["listing_url"] = href

    # Image URL
    img_el = card.select_one("img[src], img[data-src]")
    if img_el:
        listing["image_url"] = img_el.get("data-src") or img_el.get("src", "")

    # Description
    desc_el = card.select_one('[class*="description"], [class*="remarks"]')
    if desc_el:
        listing["description"] = desc_el.get_text(strip=True)[:300]

    # Location parsing from address
    if listing["address"]:
        parts = listing["address"].split(",")
        if len(parts) >= 2:
            listing["address"] = parts[0].strip()
            rest = ",".join(parts[1:]).strip()
            state_zip = rest.split()
            if state_zip:
                listing["city"] = " ".join(state_zip[:-2]) if len(state_zip) > 2 else state_zip[0]
                if len(state_zip) >= 2:
                    listing["state"] = state_zip[-2]
                if len(state_zip) >= 3:
                    listing["zip"] = state_zip[-1]

    return listing


def write_csv(listings):
    """Write listings to CSV file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(listings)


def generate_sample_data():
    """Generate sample property data when scraping fails."""
    import random

    streets = [
        "High Street", "Church Lane", "Mill Road", "Park Avenue", "Victoria Road",
        "Kings Road", "Queens Drive", "Station Road", "Manor Way", "Elm Grove",
        "Oakfield Road", "Priory Lane", "Castle Street", "Bridge Road", "Meadow Close",
        "Willow Crescent", "Rosemary Gardens", "Thornton Place", "Chestnut Drive", "Bakers Row",
    ]
    cities_states = [
        ("London", "England", "SW1A"),
        ("Manchester", "England", "M1"),
        ("Birmingham", "England", "B1"),
        ("Edinburgh", "Scotland", "EH1"),
        ("Bristol", "England", "BS1"),
        ("Liverpool", "England", "L1"),
    ]
    descriptions = [
        "Beautiful period home with open-plan living, updated kitchen with granite worktops, and spacious rear garden.",
        "Charming Victorian property featuring original hardwood floors, bay windows, and a converted loft.",
        "Modern home with smart features, energy-efficient appliances, and a stunning master bedroom with en-suite.",
        "Cosy terraced house with a fireplace, conservatory, and mature garden in a quiet neighbourhood.",
        "Spacious family home with a south-facing garden, utility room, and recently renovated bathrooms.",
        "Elegant detached house with high ceilings, period features, and a bespoke kitchen with island.",
        "Updated property with new roof, central heating, and fresh decor throughout. Chain-free and move-in ready!",
        "End-of-terrace home with driveway parking, large garden, and a detached garage.",
    ]

    random.seed(42)
    listings = []

    for i in range(60):
        city, state, zip_prefix = random.choice(cities_states)
        beds = random.choice([2, 3, 3, 3, 4, 4, 4, 5])
        baths = random.choice([1, 2, 2, 2, 3, 3])
        sqft = random.randint(1000, 4500)
        price = int(sqft * random.uniform(150, 450) / 1000) * 1000
        street_num = random.randint(100, 9999)
        street = random.choice(streets)
        zip_code = f"{zip_prefix} {random.randint(1, 9)}{random.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}{random.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}"

        listings.append({
            "id": str(i + 1),
            "price": str(price),
            "address": f"{street_num} {street}",
            "city": city,
            "state": state,
            "zip": zip_code,
            "bedrooms": str(beds),
            "bathrooms": str(baths),
            "sqft": str(sqft),
            "description": random.choice(descriptions),
            "listing_url": f"/property/{i + 1}",
            "image_url": f"https://images.unsplash.com/photo-{random.choice(['1564013799919-ab600027ffc6', '1600596542815-ffad4c1539a9', '1600585154340-be6161a56a0c', '1605276374104-dee2a0ed3cd6', '1600047509807-ba8f99d2cdde', '1583608205776-bfd35f0d9f83'])}?w=400&h=300&fit=crop",
        })

    write_csv(listings)
    print(f"Generated {len(listings)} sample listings in {CSV_PATH}")


if __name__ == "__main__":
    scrape_homes()

"""Skyscanner flight deal scraper.

Scrapes Skyscanner's deals and cheap flights pages for discounted airfare.
These are curated deals — no user search needed.

Affiliate program: Skyscanner via Impact Radius (impact.com)
"""

import re
from urllib.parse import quote_plus
from scrapers.base import BaseScraper

try:
    from config import SKYSCANNER_AFFILIATE_TAG
except ImportError:
    SKYSCANNER_AFFILIATE_TAG = ""

# Pages to scrape for flight deals
DEAL_PAGES = [
    "https://www.skyscanner.com/flights-deals",
    "https://www.skyscanner.com/flights/cheap-flights",
    "https://www.skyscanner.com/flights/deals-of-the-day",
]


class SkyscannerScraper(BaseScraper):
    site_name = "Skyscanner"
    base_url = "https://www.skyscanner.com"

    def build_affiliate_url(self, url):
        """Build Skyscanner affiliate URL via Impact Radius."""
        if not SKYSCANNER_AFFILIATE_TAG:
            return url
        encoded = quote_plus(url)
        return (
            f"https://www.skyscanner.com/g/referrals/"
            f"{SKYSCANNER_AFFILIATE_TAG}?url={encoded}"
        )

    def scrape_product(self, url):
        """Scrape a single Skyscanner deal/flight page."""
        soup = self.fetch_page(url)
        if not soup:
            return None

        title = None
        for selector in [
            ("h1", {}),
            ("div", {"class": re.compile(r"flight-title|route", re.I)}),
        ]:
            el = soup.find(*selector)
            if el:
                title = el.get_text(strip=True)
                break
        if not title:
            title = "Skyscanner Flight Deal"

        price = None
        price_selectors = [
            ("span", {"class": re.compile(r"price|fare|cost", re.I)}),
            ("div", {"class": re.compile(r"price", re.I)}),
            ("span", {"itemprop": "price"}),
        ]
        for tag, attrs in price_selectors:
            el = soup.find(tag, attrs)
            if el:
                price = self.extract_price(el.get_text())
                if price:
                    break

        return {
            "product_id": url,
            "title": title[:200],
            "price": price,
            "url": url,
            "affiliate_url": self.build_affiliate_url(url),
            "store": "Skyscanner",
            "site": "skyscanner",
            "category": "flights",
        }

    def scrape_deals(self):
        """Scrape Skyscanner deal pages for cheap flight deals."""
        all_deals = []

        for page_url in DEAL_PAGES:
            soup = self.fetch_page(page_url)
            if not soup:
                continue

            # Try multiple card selectors (Skyscanner updates their DOM)
            cards = soup.find_all("a", {"class": re.compile(r"deal|flight-card|destination", re.I)})
            if not cards:
                cards = soup.find_all("div", {"class": re.compile(r"deal-card|flight-deal|result", re.I)})
            if not cards:
                cards = soup.find_all("li", {"class": re.compile(r"deal|destination", re.I)})

            for card in cards[:20]:
                try:
                    if card.name == "a":
                        link = card
                    else:
                        link = card.find("a", href=True)
                    if not link or not link.get("href"):
                        continue

                    href = link["href"]
                    if not href.startswith("http"):
                        href = self.base_url + href

                    # Destination/route name
                    title_el = card.find(["h3", "h4", "span", "div"], {
                        "class": re.compile(r"destination|route|city|title", re.I)
                    })
                    title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
                    if not title or len(title) < 3:
                        continue

                    # Price
                    price = None
                    price_el = card.find(["span", "div"], {"class": re.compile(r"price|fare|cost", re.I)})
                    if price_el:
                        price = self.extract_price(price_el.get_text())

                    # Dates if available
                    dates = None
                    date_el = card.find(["span", "div"], {"class": re.compile(r"date|when|period", re.I)})
                    if date_el:
                        dates = date_el.get_text(strip=True)

                    deal_title = f"Flight: {title}"
                    if dates:
                        deal_title += f" ({dates})"

                    all_deals.append({
                        "product_id": href,
                        "title": deal_title[:200],
                        "price": price,
                        "url": href,
                        "affiliate_url": self.build_affiliate_url(href),
                        "store": "Skyscanner",
                        "site": "skyscanner",
                        "category": "flights",
                    })
                except Exception:
                    continue

        return all_deals

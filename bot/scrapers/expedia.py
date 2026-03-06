"""Expedia holiday/vacation package deal scraper.

Scrapes Expedia's deals pages for discounted travel packages,
hotel deals, and vacation bundles.

Affiliate program: Expedia via CJ Affiliate (cj.com) or Partnerize
"""

import re
from urllib.parse import quote_plus
from scrapers.base import BaseScraper

try:
    from config import EXPEDIA_AFFILIATE_TAG
except ImportError:
    EXPEDIA_AFFILIATE_TAG = ""

# Pages to scrape for holiday package deals
DEAL_PAGES = [
    "https://www.expedia.com/deals",
    "https://www.expedia.com/vacation-packages-deals",
    "https://www.expedia.com/Hotel-Deals",
    "https://www.expedia.com/lp/deals/bundle",
]


class ExpediaScraper(BaseScraper):
    site_name = "Expedia"
    base_url = "https://www.expedia.com"

    def build_affiliate_url(self, url):
        """Build Expedia affiliate URL."""
        if not EXPEDIA_AFFILIATE_TAG:
            return url
        encoded = quote_plus(url)
        return (
            f"https://www.expedia.com/affiliate/"
            f"{EXPEDIA_AFFILIATE_TAG}?url={encoded}"
        )

    def scrape_product(self, url):
        """Scrape a single Expedia deal/package page."""
        soup = self.fetch_page(url)
        if not soup:
            return None

        title = None
        for selector in [
            ("h1", {"class": re.compile(r"title|heading|hotel-name", re.I)}),
            ("h1", {}),
        ]:
            el = soup.find(*selector)
            if el:
                title = el.get_text(strip=True)
                break
        if not title:
            title = "Expedia Travel Deal"

        price = None
        price_selectors = [
            ("span", {"class": re.compile(r"price|cost|rate", re.I)}),
            ("div", {"class": re.compile(r"price", re.I)}),
            ("span", {"itemprop": "price"}),
        ]
        for tag, attrs in price_selectors:
            el = soup.find(tag, attrs)
            if el:
                price = self.extract_price(el.get_text())
                if price:
                    break

        original_price = None
        orig_el = soup.find("span", {"class": re.compile(r"original|strikethrough|was-price", re.I)})
        if orig_el:
            original_price = self.extract_price(orig_el.get_text())

        image_url = None
        img_el = soup.find("img", {"class": re.compile(r"hero|gallery|hotel", re.I)})
        if img_el and img_el.get("src"):
            image_url = img_el["src"]

        return {
            "product_id": url,
            "title": title[:200],
            "price": price,
            "original_price": original_price,
            "image_url": image_url,
            "url": url,
            "affiliate_url": self.build_affiliate_url(url),
            "store": "Expedia",
            "site": "expedia",
            "category": "holiday_packages",
        }

    def scrape_deals(self):
        """Scrape Expedia deal pages for vacation/hotel deals."""
        all_deals = []

        for page_url in DEAL_PAGES:
            soup = self.fetch_page(page_url)
            if not soup:
                continue

            cards = soup.find_all("div", {"class": re.compile(r"deal-card|offer-card|deal", re.I)})
            if not cards:
                cards = soup.find_all("a", {"class": re.compile(r"deal|offer|card", re.I)})
            if not cards:
                cards = soup.find_all("li", {"class": re.compile(r"deal|offer", re.I)})

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

                    # Destination/package name
                    title_el = card.find(["h3", "h4", "span", "div"], {
                        "class": re.compile(r"title|destination|name|heading", re.I)
                    })
                    title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
                    if not title or len(title) < 5:
                        continue

                    # Price
                    price = None
                    price_el = card.find(["span", "div"], {"class": re.compile(r"price|cost|rate", re.I)})
                    if price_el:
                        price = self.extract_price(price_el.get_text())

                    # Original price
                    original_price = None
                    orig_el = card.find("span", {"class": re.compile(r"original|was|strikethrough", re.I)})
                    if orig_el:
                        original_price = self.extract_price(orig_el.get_text())

                    # Discount text
                    discount_text = None
                    disc_el = card.find("span", {"class": re.compile(r"discount|savings|off", re.I)})
                    if disc_el:
                        discount_text = disc_el.get_text(strip=True)

                    deal_title = title
                    if discount_text:
                        deal_title = f"{title} - {discount_text}"

                    all_deals.append({
                        "product_id": href,
                        "title": deal_title[:200],
                        "price": price,
                        "original_price": original_price,
                        "url": href,
                        "affiliate_url": self.build_affiliate_url(href),
                        "store": "Expedia",
                        "site": "expedia",
                        "category": "holiday_packages",
                    })
                except Exception:
                    continue

        return all_deals

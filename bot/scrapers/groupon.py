"""Groupon deal scraper for events, gifts, and experiences.

Scrapes Groupon's category pages for deals on:
- Birthday gift packages
- Party deals
- Wedding packages
- Baby shower gifts
- Local experiences and events

Affiliate program: Groupon via Impact Radius (impact.com)
"""

import re
from urllib.parse import quote_plus
from scrapers.base import BaseScraper

try:
    from config import GROUPON_AFFILIATE_TAG
except ImportError:
    GROUPON_AFFILIATE_TAG = ""

# Category URLs on Groupon
CATEGORY_URLS = {
    "birthday": [
        "https://www.groupon.com/occasion/birthday-gifts",
        "https://www.groupon.com/local/birthday",
    ],
    "party": [
        "https://www.groupon.com/local/party",
        "https://www.groupon.com/browse/things-to-do",
    ],
    "wedding": [
        "https://www.groupon.com/occasion/wedding-gifts",
        "https://www.groupon.com/local/wedding",
    ],
    "baby_shower": [
        "https://www.groupon.com/occasion/baby-gifts",
        "https://www.groupon.com/occasion/new-baby",
    ],
    "gifts": [
        "https://www.groupon.com/goods/gifts",
        "https://www.groupon.com/occasion/gifts-for-her",
    ],
}


class GrouponScraper(BaseScraper):
    site_name = "Groupon"
    base_url = "https://www.groupon.com"

    def build_affiliate_url(self, url):
        """Build Groupon affiliate URL via Impact Radius."""
        if not GROUPON_AFFILIATE_TAG:
            return url
        encoded = quote_plus(url)
        return (
            f"https://www.groupon.com/visitor_referral/h/"
            f"{GROUPON_AFFILIATE_TAG}?url={encoded}"
        )

    def scrape_product(self, url):
        """Scrape a single Groupon deal page."""
        soup = self.fetch_page(url)
        if not soup:
            return None

        title = None
        for selector in [
            ("h1", {"class": re.compile(r"deal-title|merchant-name", re.I)}),
            ("h1", {}),
        ]:
            el = soup.find(*selector)
            if el:
                title = el.get_text(strip=True)
                break
        if not title:
            title = "Groupon Deal"

        price = None
        price_selectors = [
            ("span", {"class": re.compile(r"discount-price|price-value", re.I)}),
            ("span", {"class": re.compile(r"deal-price", re.I)}),
            ("span", {"itemprop": "price"}),
        ]
        for tag, attrs in price_selectors:
            el = soup.find(tag, attrs)
            if el:
                price = self.extract_price(el.get_text())
                if price:
                    break

        original_price = None
        orig_el = soup.find("span", {"class": re.compile(r"original-price|value", re.I)})
        if orig_el:
            original_price = self.extract_price(orig_el.get_text())

        image_url = None
        img_el = soup.find("img", {"class": re.compile(r"deal-image|hero", re.I)})
        if not img_el:
            img_el = soup.find("img", src=re.compile(r"groupon", re.I))
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
            "site": "groupon",
        }

    def _scrape_category_page(self, url, category):
        """Scrape a Groupon category page for deals."""
        soup = self.fetch_page(url)
        if not soup:
            return []

        deals = []
        cards = soup.find_all("div", {"class": re.compile(r"deal-card|cui-card|card-ui", re.I)})
        if not cards:
            cards = soup.find_all("figure", {"class": re.compile(r"card", re.I)})
        if not cards:
            cards = soup.find_all("a", {"class": re.compile(r"deal-link|card-link", re.I)})

        for card in cards[:15]:
            try:
                link = card if card.name == "a" else card.find("a", href=True)
                if not link or not link.get("href"):
                    continue

                href = link["href"]
                if not href.startswith("http"):
                    href = self.base_url + href

                title_el = card.find(["h3", "h4", "span"], {"class": re.compile(r"title|name|deal-title", re.I)})
                title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                price = None
                price_el = card.find("span", {"class": re.compile(r"price|discount", re.I)})
                if price_el:
                    price = self.extract_price(price_el.get_text())

                original_price = None
                orig_el = card.find("span", {"class": re.compile(r"original|was|value", re.I)})
                if orig_el:
                    original_price = self.extract_price(orig_el.get_text())

                discount_text = None
                disc_el = card.find("span", {"class": re.compile(r"discount-percent|off", re.I)})
                if disc_el:
                    discount_text = disc_el.get_text(strip=True)

                deals.append({
                    "product_id": href,
                    "title": title[:200],
                    "price": price,
                    "original_price": original_price,
                    "discount_text": discount_text,
                    "url": href,
                    "affiliate_url": self.build_affiliate_url(href),
                    "store": "Groupon",
                    "site": "groupon",
                    "category": category,
                })
            except Exception:
                continue

        return deals

    def scrape_deals(self):
        """Scrape all Groupon category pages for event/gift deals."""
        all_deals = []
        for category, urls in CATEGORY_URLS.items():
            for url in urls:
                deals = self._scrape_category_page(url, category)
                all_deals.extend(deals)
        return all_deals

    def scrape_category(self, category):
        """Scrape deals for a specific category only."""
        urls = CATEGORY_URLS.get(category, [])
        all_deals = []
        for url in urls:
            deals = self._scrape_category_page(url, category)
            all_deals.extend(deals)
        return all_deals

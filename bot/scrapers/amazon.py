"""Amazon product scraper."""

import re
from scrapers.base import BaseScraper

# Load affiliate tag from config
try:
    from config import AMAZON_AFFILIATE_TAG
except ImportError:
    AMAZON_AFFILIATE_TAG = "yourtag-20"


class AmazonScraper(BaseScraper):
    site_name = "Amazon"
    base_url = "https://www.amazon.com"

    def extract_asin(self, url):
        """Extract ASIN from an Amazon URL."""
        patterns = [
            r'/dp/([A-Z0-9]{10})',
            r'/gp/product/([A-Z0-9]{10})',
            r'/ASIN/([A-Z0-9]{10})',
            r'asin=([A-Z0-9]{10})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def build_affiliate_url(self, url_or_asin):
        """Build Amazon URL with affiliate tag."""
        asin = url_or_asin if len(url_or_asin) == 10 else self.extract_asin(url_or_asin)
        if asin:
            return f"https://www.amazon.com/dp/{asin}?tag={AMAZON_AFFILIATE_TAG}"
        return url_or_asin

    def scrape_product(self, url_or_asin):
        """Scrape an Amazon product page."""
        if len(url_or_asin) == 10 and url_or_asin.isalnum():
            asin = url_or_asin
            url = f"https://www.amazon.com/dp/{asin}"
        else:
            asin = self.extract_asin(url_or_asin)
            url = url_or_asin
            if not asin:
                print(f"[Amazon] Could not extract ASIN from: {url_or_asin}")
                return None

        soup = self.fetch_page(url)
        if not soup:
            return None

        # Title
        title = None
        for selector in [("span", {"id": "productTitle"}), ("h1", {"id": "title"})]:
            el = soup.find(*selector)
            if el:
                title = el.get_text(strip=True)
                break
        if not title:
            title = f"Amazon Product {asin}"

        # Price
        price = None
        price_selectors = [
            ("span", {"class": "a-price-whole"}),
            ("span", {"id": "priceblock_ourprice"}),
            ("span", {"id": "priceblock_dealprice"}),
            ("span", {"id": "priceblock_saleprice"}),
            ("span", {"class": "a-offscreen"}),
        ]
        for tag, attrs in price_selectors:
            el = soup.find(tag, attrs)
            if el:
                price_text = el.get_text(strip=True)
                if attrs.get("class") == "a-price-whole":
                    fraction_el = soup.find("span", {"class": "a-price-fraction"})
                    fraction = fraction_el.get_text(strip=True) if fraction_el else "00"
                    price = self.extract_price(f"{price_text}.{fraction}")
                else:
                    price = self.extract_price(price_text)
                if price:
                    break

        # Image
        image_url = None
        for img_id in ["landingImage", "imgBlkFront"]:
            img_el = soup.find("img", {"id": img_id})
            if img_el and img_el.get("src"):
                image_url = img_el["src"]
                break

        # Category (from breadcrumb navigation)
        category = None
        breadcrumb = soup.find("div", {"id": "wayfinding-breadcrumbs_container"})
        if breadcrumb:
            crumbs = breadcrumb.find_all("a")
            if crumbs:
                category = crumbs[0].get_text(strip=True)
        if not category:
            # Fallback: try the department nav
            dept = soup.find("a", {"id": "nav-subnav"})
            if dept:
                category = dept.get_text(strip=True)

        return {
            "product_id": asin,
            "title": title[:200],
            "price": price,
            "image_url": image_url,
            "url": url,
            "affiliate_url": self.build_affiliate_url(asin),
            "site": "amazon",
            "category": category,
        }

    def scrape_deals(self):
        """Scrape Amazon's Today's Deals page."""
        soup = self.fetch_page("https://www.amazon.com/deals")
        if not soup:
            return []

        deals = []
        deal_cards = soup.find_all("div", {"class": re.compile(r"DealCard|deal-card", re.I)})

        for card in deal_cards[:20]:
            try:
                link = card.find("a", href=True)
                if not link:
                    continue

                href = link["href"]
                if not href.startswith("http"):
                    href = self.base_url + href

                title_el = card.find("span", {"class": re.compile(r"Title|title")})
                title = title_el.get_text(strip=True) if title_el else "Amazon Deal"

                price_el = card.find("span", {"class": re.compile(r"price|Price")})
                price = self.extract_price(price_el.get_text()) if price_el else None

                asin = self.extract_asin(href)

                deals.append({
                    "product_id": asin or href,
                    "title": title[:200],
                    "price": price,
                    "url": href,
                    "affiliate_url": self.build_affiliate_url(href) if asin else href,
                    "site": "amazon",
                })
            except Exception:
                continue

        return deals

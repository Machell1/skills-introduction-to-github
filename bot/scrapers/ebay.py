"""eBay product scraper."""

import re
from urllib.parse import quote_plus
from scrapers.base import BaseScraper

try:
    from config import EBAY_AFFILIATE_CAMPAIGN_ID
except ImportError:
    EBAY_AFFILIATE_CAMPAIGN_ID = ""


class EbayScraper(BaseScraper):
    site_name = "eBay"
    base_url = "https://www.ebay.com"

    def extract_item_id(self, url):
        """Extract item ID from an eBay URL."""
        patterns = [
            r'/itm/(?:[^/]+/)?(\d+)',
            r'/itm/(\d+)',
            r'item=(\d+)',
            r'ViewItem.*?item=(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def build_affiliate_url(self, url):
        """Build eBay Partner Network affiliate URL."""
        if not EBAY_AFFILIATE_CAMPAIGN_ID:
            return url
        encoded = quote_plus(url)
        return (
            f"https://rover.ebay.com/rover/1/{EBAY_AFFILIATE_CAMPAIGN_ID}/1"
            f"?mpre={encoded}&toolid=10001&campid={EBAY_AFFILIATE_CAMPAIGN_ID}"
        )

    def scrape_product(self, url):
        """Scrape an eBay product listing page."""
        item_id = self.extract_item_id(url)
        if not item_id:
            print(f"[eBay] Could not extract item ID from: {url}")
            return None

        soup = self.fetch_page(url)
        if not soup:
            return None

        # Title
        title = None
        for selector in [
            ("h1", {"class": re.compile(r"x-item-title")}),
            ("h1", {"id": "itemTitle"}),
            ("span", {"id": "itemTitle"}),
            ("h1", {}),
        ]:
            el = soup.find(*selector)
            if el:
                title = el.get_text(strip=True)
                # Remove "Details about" prefix eBay sometimes adds
                title = re.sub(r'^Details about\s*', '', title)
                break
        if not title:
            title = f"eBay Item {item_id}"

        # Price
        price = None
        price_selectors = [
            ("span", {"class": re.compile(r"x-price-primary")}),
            ("span", {"id": "prcIsum"}),
            ("span", {"id": "prcIsum_bid498"}),
            ("span", {"class": re.compile(r"notranslate")}),
            ("span", {"itemprop": "price"}),
        ]
        for tag, attrs in price_selectors:
            el = soup.find(tag, attrs)
            if el:
                price_text = el.get_text(strip=True)
                price = self.extract_price(price_text)
                if price:
                    break

        # Also check meta tag for price
        if not price:
            meta_price = soup.find("meta", {"itemprop": "price"})
            if meta_price and meta_price.get("content"):
                price = self.extract_price(meta_price["content"])

        # Image
        image_url = None
        img_el = soup.find("img", {"id": "icImg"})
        if not img_el:
            img_el = soup.find("img", {"class": re.compile(r"ux-image-carousel")})
        if not img_el:
            img_el = soup.find("div", {"class": re.compile(r"image")})
            if img_el:
                img_el = img_el.find("img")
        if img_el and img_el.get("src"):
            image_url = img_el["src"]

        return {
            "product_id": item_id,
            "title": title[:200],
            "price": price,
            "image_url": image_url,
            "url": url,
            "affiliate_url": self.build_affiliate_url(url),
            "site": "ebay",
        }

    def scrape_deals(self):
        """Scrape eBay Daily Deals page."""
        soup = self.fetch_page("https://www.ebay.com/deals")
        if not soup:
            return []

        deals = []
        deal_cards = soup.find_all("div", {"class": re.compile(r"dne-itemtile|ebayui-dne-item-featured-card")})

        for card in deal_cards[:20]:
            try:
                link = card.find("a", href=True)
                if not link:
                    continue

                href = link["href"]
                if not href.startswith("http"):
                    href = self.base_url + href

                title_el = card.find("span", {"class": re.compile(r"dne-itemtile-title|title")})
                title = title_el.get_text(strip=True) if title_el else "eBay Deal"

                price_el = card.find("span", {"class": re.compile(r"dne-itemtile-price|first")})
                price = self.extract_price(price_el.get_text()) if price_el else None

                orig_el = card.find("span", {"class": re.compile(r"dne-itemtile-original|strikethrough")})
                original_price = self.extract_price(orig_el.get_text()) if orig_el else None

                item_id = self.extract_item_id(href)

                deals.append({
                    "product_id": item_id or href,
                    "title": title[:200],
                    "price": price,
                    "original_price": original_price,
                    "url": href,
                    "affiliate_url": self.build_affiliate_url(href),
                    "site": "ebay",
                })
            except Exception:
                continue

        return deals

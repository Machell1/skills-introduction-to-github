"""Base scraper class for all site scrapers."""

import time
import random
import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 15


class BaseScraper:
    """Base class for all site scrapers."""

    site_name = "unknown"
    base_url = ""

    def get_headers(self):
        return {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

    def fetch_page(self, url):
        """Fetch a page with rate limiting and error handling."""
        time.sleep(random.uniform(1.5, 4))
        try:
            response = requests.get(
                url, headers=self.get_headers(), timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            return BeautifulSoup(response.text, "html.parser")
        except requests.RequestException as e:
            print(f"[{self.site_name}] Request failed for {url}: {e}")
            return None

    def scrape_product(self, url):
        """
        Scrape a single product page. Must be implemented by subclasses.

        Returns dict: {product_id, title, price, image_url, url, affiliate_url, site}
        """
        raise NotImplementedError

    def scrape_deals(self):
        """
        Scrape current deals/sales page. Override in subclasses.

        Returns list of dicts: [{product_id, title, price, original_price, url, ...}]
        """
        return []

    def scrape_category(self, category):
        """Scrape deals for a specific category. Override in subclasses that support categories."""
        return []

    def build_affiliate_url(self, url):
        """Build an affiliate URL. Override per site."""
        return url

    def extract_price(self, text):
        """Extract a float price from text like '$29.99' or '29.99'."""
        if not text:
            return None
        import re
        text = re.sub(r'[^\d.,]', '', text.strip())
        text = text.replace(',', '')
        try:
            return float(text)
        except (ValueError, TypeError):
            return None

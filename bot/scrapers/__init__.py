"""Multi-site deal scrapers."""

from scrapers.amazon import AmazonScraper
from scrapers.bestbuy import BestBuyScraper
from scrapers.walmart import WalmartScraper
from scrapers.target import TargetScraper
from scrapers.slickdeals import SlickdealsScraper
from scrapers.dealnews import DealNewsScraper
from scrapers.ebay import EbayScraper
from scrapers.groupon import GrouponScraper
from scrapers.skyscanner import SkyscannerScraper
from scrapers.expedia import ExpediaScraper
from scrapers.base import BaseScraper

# All available scrapers
ALL_SCRAPERS = {
    "amazon": AmazonScraper,
    "bestbuy": BestBuyScraper,
    "walmart": WalmartScraper,
    "target": TargetScraper,
    "ebay": EbayScraper,
}

# Deal aggregators (scrape curated deal feeds)
DEAL_AGGREGATORS = {
    "slickdeals": SlickdealsScraper,
    "dealnews": DealNewsScraper,
}

# Lifestyle & travel deal scrapers (events, gifts, flights, packages)
LIFESTYLE_SCRAPERS = {
    "groupon": GrouponScraper,
    "skyscanner": SkyscannerScraper,
    "expedia": ExpediaScraper,
}

# Deal categories for lifestyle scrapers
DEAL_CATEGORIES = {
    "flights": "Flights",
    "holiday_packages": "Holiday Packages",
    "birthday": "Birthday Gifts",
    "party": "Party Deals",
    "wedding": "Wedding Packages",
    "baby_shower": "Baby Shower Gifts",
    "gifts": "Gift Ideas",
}


def get_scraper_for_url(url):
    """Return the appropriate scraper class for a given URL."""
    url_lower = url.lower()
    if "amazon.com" in url_lower or "amzn.to" in url_lower:
        return AmazonScraper()
    elif "bestbuy.com" in url_lower:
        return BestBuyScraper()
    elif "walmart.com" in url_lower:
        return WalmartScraper()
    elif "target.com" in url_lower:
        return TargetScraper()
    elif "ebay.com" in url_lower:
        return EbayScraper()
    elif "slickdeals.net" in url_lower:
        return SlickdealsScraper()
    elif "dealnews.com" in url_lower:
        return DealNewsScraper()
    elif "groupon.com" in url_lower:
        return GrouponScraper()
    elif "skyscanner.com" in url_lower:
        return SkyscannerScraper()
    elif "expedia.com" in url_lower:
        return ExpediaScraper()
    return None


def detect_site(url):
    """Detect which site a URL belongs to."""
    url_lower = url.lower()
    if "amazon.com" in url_lower or "amzn.to" in url_lower:
        return "amazon"
    elif "bestbuy.com" in url_lower:
        return "bestbuy"
    elif "walmart.com" in url_lower:
        return "walmart"
    elif "target.com" in url_lower:
        return "target"
    elif "ebay.com" in url_lower:
        return "ebay"
    elif "slickdeals.net" in url_lower:
        return "slickdeals"
    elif "dealnews.com" in url_lower:
        return "dealnews"
    elif "groupon.com" in url_lower:
        return "groupon"
    elif "skyscanner.com" in url_lower:
        return "skyscanner"
    elif "expedia.com" in url_lower:
        return "expedia"
    return "unknown"

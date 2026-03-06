"""
Multi-site product scraper - delegates to site-specific scrapers.

Supported sites: Amazon, Best Buy, Walmart, Target, eBay
Deal aggregators: Slickdeals, DealNews
Lifestyle deals: Groupon, Skyscanner, Expedia
"""

from scrapers import get_scraper_for_url, detect_site, ALL_SCRAPERS, DEAL_AGGREGATORS, LIFESTYLE_SCRAPERS
from scrapers.groupon import GrouponScraper
from scrapers.skyscanner import SkyscannerScraper
from scrapers.expedia import ExpediaScraper


def scrape_product(url_or_id):
    """Scrape a product from any supported site. Auto-detects the site from the URL."""
    scraper = get_scraper_for_url(url_or_id)
    if scraper:
        return scraper.scrape_product(url_or_id)

    # If no scraper matched, try Amazon (for bare ASINs)
    if len(url_or_id) == 10 and url_or_id.isalnum():
        from scrapers.amazon import AmazonScraper
        return AmazonScraper().scrape_product(url_or_id)

    print(f"[Scraper] Unsupported URL: {url_or_id}")
    print(f"[Scraper] Supported: Amazon, Best Buy, Walmart, Target, eBay, Groupon, Skyscanner, Expedia")
    return None


def scrape_deals_from_site(site_name):
    """Scrape current deals from a specific retailer."""
    site_name = site_name.lower()
    scraper_class = ALL_SCRAPERS.get(site_name)
    if scraper_class:
        scraper = scraper_class()
        return scraper.scrape_deals()

    print(f"[Scraper] Unknown site: {site_name}")
    return []


def scrape_deal_aggregators():
    """Scrape all deal aggregator sites for current hot deals."""
    all_deals = []
    for name, scraper_class in DEAL_AGGREGATORS.items():
        print(f"[Scraper] Scanning {name}...")
        scraper = scraper_class()
        deals = scraper.scrape_deals()
        print(f"[Scraper] Found {len(deals)} deals on {name}")
        all_deals.extend(deals)
    return all_deals


def scrape_all_deals():
    """Scrape deals from all retailers and aggregators."""
    all_deals = []

    # Retailer deal pages
    for name, scraper_class in ALL_SCRAPERS.items():
        print(f"[Scraper] Scanning {name} deals...")
        scraper = scraper_class()
        deals = scraper.scrape_deals()
        print(f"[Scraper] Found {len(deals)} deals on {name}")
        all_deals.extend(deals)

    # Aggregator sites
    for name, scraper_class in DEAL_AGGREGATORS.items():
        print(f"[Scraper] Scanning {name}...")
        scraper = scraper_class()
        deals = scraper.scrape_deals()
        print(f"[Scraper] Found {len(deals)} deals on {name}")
        all_deals.extend(deals)

    # Lifestyle deal sites
    for name, scraper_class in LIFESTYLE_SCRAPERS.items():
        print(f"[Scraper] Scanning {name} lifestyle deals...")
        scraper = scraper_class()
        deals = scraper.scrape_deals()
        print(f"[Scraper] Found {len(deals)} deals on {name}")
        all_deals.extend(deals)

    return all_deals


def scrape_lifestyle_deals():
    """Scrape lifestyle deal sites (flights, packages, gifts, events)."""
    all_deals = []
    for name, scraper_class in LIFESTYLE_SCRAPERS.items():
        print(f"[Scraper] Scanning {name} for lifestyle deals...")
        scraper = scraper_class()
        deals = scraper.scrape_deals()
        print(f"[Scraper] Found {len(deals)} deals on {name}")
        all_deals.extend(deals)
    return all_deals


def scrape_category_deals(category):
    """Scrape deals for a specific category (e.g. 'flights', 'birthday', 'wedding')."""
    all_deals = []

    # Groupon handles event/gift categories
    if category in ("birthday", "party", "wedding", "baby_shower", "gifts"):
        scraper = GrouponScraper()
        all_deals.extend(scraper.scrape_category(category))

    # Skyscanner handles flights
    if category == "flights":
        scraper = SkyscannerScraper()
        all_deals.extend(scraper.scrape_deals())

    # Expedia handles holiday packages
    if category == "holiday_packages":
        scraper = ExpediaScraper()
        all_deals.extend(scraper.scrape_deals())

    return all_deals

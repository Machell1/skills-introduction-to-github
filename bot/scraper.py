"""Amazon product price scraper."""

import re
import time
import random
import requests
from bs4 import BeautifulSoup
from config import USER_AGENT, REQUEST_TIMEOUT, AMAZON_AFFILIATE_TAG


def extract_asin(url):
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


def build_affiliate_url(asin):
    """Build an Amazon URL with the affiliate tag."""
    return f"https://www.amazon.com/dp/{asin}?tag={AMAZON_AFFILIATE_TAG}"


def scrape_product(url_or_asin):
    """
    Scrape product info from Amazon.

    Returns dict with: title, price, image_url, asin, affiliate_url
    Returns None if scraping fails.
    """
    # Determine ASIN
    if len(url_or_asin) == 10 and url_or_asin.isalnum():
        asin = url_or_asin
        url = f"https://www.amazon.com/dp/{asin}"
    else:
        asin = extract_asin(url_or_asin)
        url = url_or_asin
        if not asin:
            print(f"[Scraper] Could not extract ASIN from: {url_or_asin}")
            return None

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }

    # Random delay to be respectful
    time.sleep(random.uniform(1, 3))

    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[Scraper] Request failed for {asin}: {e}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # Extract title
    title = None
    title_el = soup.find("span", {"id": "productTitle"})
    if title_el:
        title = title_el.get_text(strip=True)
    if not title:
        title_el = soup.find("h1", {"id": "title"})
        if title_el:
            title = title_el.get_text(strip=True)
    if not title:
        title = f"Amazon Product {asin}"

    # Extract price - try multiple selectors
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
            # Clean the price string
            price_text = re.sub(r'[^\d.,]', '', price_text)
            price_text = price_text.replace(',', '')
            if price_text:
                try:
                    # Handle "whole" + "fraction" pattern
                    if attrs.get("class") == "a-price-whole":
                        fraction_el = soup.find("span", {"class": "a-price-fraction"})
                        fraction = fraction_el.get_text(strip=True) if fraction_el else "00"
                        price = float(f"{price_text}.{fraction}")
                    else:
                        price = float(price_text)
                    break
                except ValueError:
                    continue

    # Extract image
    image_url = None
    img_el = soup.find("img", {"id": "landingImage"})
    if img_el and img_el.get("src"):
        image_url = img_el["src"]
    if not image_url:
        img_el = soup.find("img", {"id": "imgBlkFront"})
        if img_el and img_el.get("src"):
            image_url = img_el["src"]

    return {
        "asin": asin,
        "title": title[:200],  # Truncate long titles
        "price": price,
        "image_url": image_url,
        "url": url,
        "affiliate_url": build_affiliate_url(asin),
    }


def scrape_multiple(asins):
    """Scrape multiple products with delays between requests."""
    results = []
    for asin in asins:
        result = scrape_product(asin)
        if result:
            results.append(result)
        # Respectful delay between requests
        time.sleep(random.uniform(2, 5))
    return results

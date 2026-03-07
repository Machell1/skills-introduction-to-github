"""Revenue estimation and earnings reporting for the Deal Alert Bot."""

from database import get_commission_rate, get_earnings_summary, get_earnings_total
from config import (
    AMAZON_AFFILIATE_TAG, WALMART_AFFILIATE_TAG,
    TARGET_AFFILIATE_TAG, BESTBUY_AFFILIATE_TAG,
    EBAY_AFFILIATE_CAMPAIGN_ID, GROUPON_AFFILIATE_TAG,
    SKYSCANNER_AFFILIATE_TAG, EXPEDIA_AFFILIATE_TAG,
)

# Map site names to their configured affiliate tags
_TAG_MAP = {
    "amazon": AMAZON_AFFILIATE_TAG,
    "walmart": WALMART_AFFILIATE_TAG,
    "target": TARGET_AFFILIATE_TAG,
    "bestbuy": BESTBUY_AFFILIATE_TAG,
    "ebay": EBAY_AFFILIATE_CAMPAIGN_ID,
    "groupon": GROUPON_AFFILIATE_TAG,
    "skyscanner": SKYSCANNER_AFFILIATE_TAG,
    "expedia": EXPEDIA_AFFILIATE_TAG,
}

# Signup URLs for affiliate programs (shown in missed revenue section)
_SIGNUP_URLS = {
    "amazon": "affiliate-program.amazon.com",
    "walmart": "impact.com (Walmart program)",
    "target": "impact.com (Target program)",
    "bestbuy": "impact.com (Best Buy program)",
    "ebay": "partnernetwork.ebay.com",
    "groupon": "impact.com (Groupon program)",
    "skyscanner": "impact.com (Skyscanner program)",
    "expedia": "cj.com (Expedia program)",
}


def has_affiliate_tag(site):
    """Check if the affiliate tag is configured for a given site."""
    tag = _TAG_MAP.get(site, "")
    # Amazon default "yourtag-20" counts as not configured
    if site == "amazon" and tag == "yourtag-20":
        return False
    return bool(tag)


def estimate_commission(site, sale_price):
    """Calculate estimated commission for a deal.

    Returns (estimated_amount, has_tag).
    """
    has_tag = has_affiliate_tag(site)

    if not sale_price or sale_price <= 0:
        # For CPA sites, still return the CPA amount if tag is configured
        if has_tag:
            rate_row = get_commission_rate(site)
            if rate_row and rate_row["model"] == "cpa":
                return rate_row["cpa_amount"], has_tag
        return 0.0, has_tag

    if not has_tag:
        return 0.0, has_tag

    rate_row = get_commission_rate(site)
    if not rate_row:
        return 0.0, has_tag

    if rate_row["model"] == "cpa":
        return rate_row["cpa_amount"], has_tag
    else:
        return sale_price * rate_row["rate_used"], has_tag


def _estimate_missed(site, sale_value):
    """Estimate what commission would have been if tag was configured."""
    rate_row = get_commission_rate(site)
    if not rate_row:
        return 0.0
    if rate_row["model"] == "cpa":
        return rate_row["cpa_amount"]
    if sale_value and sale_value > 0:
        return sale_value * rate_row["rate_used"]
    return 0.0


def format_earnings_report(days=1):
    """Generate an HTML earnings report for the last N days."""
    period = "24h" if days == 1 else f"{days} days"
    summary = get_earnings_summary(days)
    totals = get_earnings_total(days)
    all_time = get_earnings_total()

    if not summary:
        return (
            f"💰 <b>EARNINGS ESTIMATE</b> (Last {period})\n\n"
            f"No deals posted in this period.\n\n"
            f"📊 All-time: ${all_time['total']:.2f} est. from {all_time['deal_count']} deals"
        )

    total_deals = totals["deal_count"]
    total_commission = totals["total"]
    deals_with_tag = sum(s["with_tag"] for s in summary)
    deals_without_tag = sum(s["without_tag"] for s in summary)

    lines = [
        f"💰 <b>EARNINGS ESTIMATE</b> (Last {period})\n",
        f"📊 Deals posted: {total_deals}",
        f"🏷️ With affiliate tags: {deals_with_tag}",
    ]
    if deals_without_tag > 0:
        lines.append(f"⚠️ Without tags: {deals_without_tag}")

    lines.append(f"\n💵 <b>Revenue by Store:</b>")

    missed_lines = []
    total_missed = 0.0

    for s in summary:
        site = s["site"]
        count = s["deal_count"]
        commission = s["total_commission"] or 0

        if commission > 0:
            lines.append(f"  {site.capitalize()}: {count} deals → ~${commission:.2f}")
        elif s["without_tag"] > 0:
            missed = _estimate_missed(site, s["total_sale_value"])
            lines.append(f"  {site.capitalize()}: {count} deals → $0.00 (no tag!)")
            if missed > 0:
                signup = _SIGNUP_URLS.get(site, "")
                missed_lines.append(f"  {site.capitalize()}: ~${missed:.2f} ({signup})")
                total_missed += missed
        elif count > 0:
            lines.append(f"  {site.capitalize()}: {count} deals → ~${commission:.2f}")

    lines.append(f"\n📈 <b>Estimated total: ~${total_commission:.2f}</b>")

    if missed_lines:
        lines.append(f"\n⚠️ <b>MISSED REVENUE:</b>")
        lines.extend(missed_lines)
        lines.append(f"  → Configure tags to capture ~${total_missed:.2f} more")

    lines.append(
        f"\n📊 All-time: ${all_time['total']:.2f} est. from {all_time['deal_count']} deals"
    )

    lines.append(
        "\nℹ️ <i>Estimates use avg commission rates.\n"
        "Check actual earnings at your affiliate dashboards.</i>"
    )

    return "\n".join(lines)

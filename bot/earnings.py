"""Revenue estimation and earnings reporting for the Deal Alert Bot."""

from database import (
    get_commission_rate, get_earnings_summary, get_earnings_total,
    get_click_counts, get_top_deals_by_clicks, get_earnings_comparison,
    get_actuals_summary,
)
from config import (
    AMAZON_AFFILIATE_TAG, WALMART_AFFILIATE_TAG,
    TARGET_AFFILIATE_TAG, BESTBUY_AFFILIATE_TAG,
    EBAY_AFFILIATE_CAMPAIGN_ID, GROUPON_AFFILIATE_TAG,
    SKYSCANNER_AFFILIATE_TAG, EXPEDIA_AFFILIATE_TAG,
    DEFAULT_CONVERSION_RATE, DEFAULT_CTR,
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
    if site == "amazon" and tag == "yourtag-20":
        return False
    return bool(tag)


def estimate_commission(site, sale_price, category=None, apply_funnel=False,
                        clicks=None):
    """Calculate estimated commission for a deal.

    Args:
        site: Store name (e.g., 'amazon', 'walmart')
        sale_price: Deal price
        category: Product category (used for Amazon category-specific rates)
        apply_funnel: If True, apply CTR and conversion rate to get realistic estimate
        clicks: Actual tracked clicks (overrides CTR estimate when available)

    Returns (estimated_amount, has_tag).
    """
    has_tag = has_affiliate_tag(site)

    if not sale_price or sale_price <= 0:
        if has_tag:
            rate_row = get_commission_rate(site)
            if rate_row and rate_row["model"] == "cpa":
                raw = rate_row["cpa_amount"]
                if apply_funnel:
                    raw = _apply_funnel(raw, clicks)
                return raw, has_tag
        return 0.0, has_tag

    if not has_tag:
        return 0.0, has_tag

    # Get the commission rate — category-specific for Amazon
    rate = _get_rate_for_deal(site, category)
    if rate is None:
        return 0.0, has_tag

    raw_commission = sale_price * rate

    if apply_funnel:
        raw_commission = _apply_funnel(raw_commission, clicks)

    return raw_commission, has_tag


def _get_rate_for_deal(site, category=None):
    """Get the commission rate for a deal, using category-specific rates for Amazon."""
    if site == "amazon" and category:
        from database import get_amazon_category_rate
        cat_rate = get_amazon_category_rate(category)
        if cat_rate is not None:
            return cat_rate

    rate_row = get_commission_rate(site)
    if not rate_row:
        return None

    if rate_row["model"] == "cpa":
        return None  # CPA handled separately
    return rate_row["rate_used"]


def _apply_funnel(raw_commission, clicks=None):
    """Apply click-through and conversion rates to raw commission estimate."""
    if clicks is not None and clicks > 0:
        estimated_conversions = clicks * DEFAULT_CONVERSION_RATE
    else:
        estimated_conversions = DEFAULT_CTR * DEFAULT_CONVERSION_RATE
    return raw_commission * estimated_conversions


def _estimate_missed(site, sale_value):
    """Estimate what commission would have been if tag was configured."""
    rate_row = get_commission_rate(site)
    if not rate_row:
        return 0.0
    if rate_row["model"] == "cpa":
        return rate_row["cpa_amount"]
    if sale_value and sale_value > 0:
        return sale_value * rate_row["rate_used"] * DEFAULT_CTR * DEFAULT_CONVERSION_RATE
    return 0.0


def format_earnings_report(days=1):
    """Generate an HTML earnings report with funnel data for the last N days."""
    period = "24h" if days == 1 else f"{days} days"
    summary = get_earnings_summary(days)
    totals = get_earnings_total(days)
    all_time = get_earnings_total()
    click_data = get_click_counts(days)
    actuals = get_actuals_summary(days)
    top_deals = get_top_deals_by_clicks(days, limit=3)
    trend = get_earnings_comparison(days)

    # Apply funnel to all-time total
    all_time_funnel = all_time["total"] * DEFAULT_CTR * DEFAULT_CONVERSION_RATE

    if not summary:
        return (
            f"💰 <b>REVENUE REPORT</b> (Last {period})\n\n"
            f"No deals posted in this period.\n\n"
            f"📊 All-time: ~${all_time_funnel:.2f} est. from {all_time['deal_count']} deals"
        )

    total_deals = totals["deal_count"]
    raw_total = totals["total"]
    deals_with_tag = sum(s["with_tag"] for s in summary)
    deals_without_tag = sum(s["without_tag"] for s in summary)

    # Aggregate click data by site
    clicks_by_site = {c["site"]: c["click_count"] for c in click_data} if click_data else {}
    total_clicks = sum(clicks_by_site.values())

    # Aggregate actual revenue by site
    actuals_by_site = {a["site"]: a for a in actuals} if actuals else {}
    total_actual = sum(a.get("commission", 0) for a in actuals_by_site.values())

    # Calculate funnel estimate
    if total_clicks > 0:
        est_conversions = total_clicks * DEFAULT_CONVERSION_RATE
        funnel_total = raw_total * (total_clicks / max(total_deals, 1)) * DEFAULT_CONVERSION_RATE
    else:
        est_conversions = total_deals * DEFAULT_CTR * DEFAULT_CONVERSION_RATE
        funnel_total = raw_total * DEFAULT_CTR * DEFAULT_CONVERSION_RATE

    # Build report
    lines = [f"💰 <b>REVENUE REPORT</b> (Last {period})\n"]

    # Funnel section
    lines.append("<b>FUNNEL:</b>")
    lines.append(f"  Deals posted: {total_deals}")
    if total_clicks > 0:
        ctr = (total_clicks / max(total_deals, 1)) * 100
        lines.append(f"  Tracked clicks: {total_clicks} ({ctr:.1f}% CTR)")
        lines.append(f"  Est. conversions: {est_conversions:.1f} ({DEFAULT_CONVERSION_RATE * 100:.0f}% rate)")
    else:
        lines.append(f"  Tracked clicks: -- (no data yet)")
        lines.append(f"  Est. conversions: {est_conversions:.2f} (using {DEFAULT_CTR * 100:.0f}% CTR, {DEFAULT_CONVERSION_RATE * 100:.0f}% conv.)")
    lines.append(f"  With affiliate tags: {deals_with_tag}")
    if deals_without_tag > 0:
        lines.append(f"  Without tags: {deals_without_tag}")

    # Revenue by store
    lines.append(f"\n<b>REVENUE BY STORE:</b>")
    missed_lines = []
    total_missed = 0.0

    for s in summary:
        site = s["site"]
        count = s["deal_count"]
        raw_commission = s["total_commission"] or 0
        site_clicks = clicks_by_site.get(site, 0)

        # Apply funnel to this site's estimate
        if site_clicks > 0:
            site_est = raw_commission * (site_clicks / max(count, 1)) * DEFAULT_CONVERSION_RATE
        else:
            site_est = raw_commission * DEFAULT_CTR * DEFAULT_CONVERSION_RATE

        # Check for actual data
        site_actual = actuals_by_site.get(site)
        actual_str = f"${site_actual['commission']:.2f}" if site_actual else "--"

        if raw_commission > 0:
            click_str = f" | {site_clicks} clicks" if site_clicks > 0 else ""
            lines.append(
                f"  {site.capitalize()}: {count} deals{click_str} | "
                f"Est: ~${site_est:.2f} | Actual: {actual_str}"
            )
        elif s["without_tag"] > 0:
            missed = _estimate_missed(site, s["total_sale_value"])
            lines.append(f"  {site.capitalize()}: {count} deals | $0.00 (no tag!)")
            if missed > 0:
                signup = _SIGNUP_URLS.get(site, "")
                missed_lines.append(f"  {site.capitalize()}: ~${missed:.2f} ({signup})")
                total_missed += missed
        elif count > 0:
            lines.append(f"  {site.capitalize()}: {count} deals | ~${site_est:.2f}")

    # Totals
    lines.append(f"\n<b>TOTALS:</b>")
    lines.append(f"  Estimated: ~${funnel_total:.2f}")
    if total_actual > 0:
        lines.append(f"  Actual (API data): ${total_actual:.2f}")
        combined = max(funnel_total, total_actual)
        lines.append(f"  Best estimate: ${combined:.2f}")

    # Trends
    if trend:
        prev_total = trend.get("previous_total", 0) * DEFAULT_CTR * DEFAULT_CONVERSION_RATE
        if prev_total > 0:
            change_pct = ((funnel_total - prev_total) / prev_total) * 100
            trend_emoji = "📈" if change_pct >= 0 else "📉"
            lines.append(f"\n{trend_emoji} vs previous {period}: {change_pct:+.0f}%")

    # Top deals by clicks
    if top_deals:
        lines.append(f"\n<b>TOP DEALS (by clicks):</b>")
        for i, deal in enumerate(top_deals, 1):
            title = (deal.get("title") or "")[:40]
            clicks = deal.get("click_count", 0)
            lines.append(f"  {i}. \"{title}\" - {clicks} clicks")

    # Missed revenue
    if missed_lines:
        lines.append(f"\n⚠️ <b>MISSED REVENUE:</b>")
        lines.extend(missed_lines)
        lines.append(f"  → Configure tags to capture ~${total_missed:.2f} more")

    # All-time
    lines.append(f"\n📊 All-time: ~${all_time_funnel:.2f} est. from {all_time['deal_count']} deals")

    lines.append(
        "\nℹ️ <i>Revenue estimates use conversion funnel modeling.\n"
        "Check actual earnings at your affiliate dashboards.</i>"
    )

    return "\n".join(lines)


def format_revenue_report(days=7):
    """Generate a detailed revenue report combining actual API data with estimates."""
    period = f"{days} days"
    summary = get_earnings_summary(days)
    totals = get_earnings_total(days)
    actuals = get_actuals_summary(days)
    click_data = get_click_counts(days)

    actuals_by_site = {a["site"]: a for a in actuals} if actuals else {}
    clicks_by_site = {c["site"]: c["click_count"] for c in click_data} if click_data else {}
    total_actual = sum(a.get("commission", 0) for a in actuals_by_site.values())

    raw_total = totals["total"] if totals else 0
    total_deals = totals["deal_count"] if totals else 0
    total_clicks = sum(clicks_by_site.values())

    # Funnel-adjusted estimate
    if total_clicks > 0:
        funnel_total = raw_total * (total_clicks / max(total_deals, 1)) * DEFAULT_CONVERSION_RATE
    else:
        funnel_total = raw_total * DEFAULT_CTR * DEFAULT_CONVERSION_RATE

    # Determine confidence
    if total_actual > 0 and funnel_total > 0:
        actual_pct = total_actual / (total_actual + funnel_total) * 100
        if actual_pct > 50:
            confidence = "HIGH"
        elif actual_pct > 20:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
    else:
        confidence = "LOW" if total_actual == 0 else "MEDIUM"

    lines = [f"💵 <b>REVENUE REPORT</b> (Last {period})\n"]

    # Per-site breakdown
    lines.append("<b>BY STORE:</b>")
    for s in (summary or []):
        site = s["site"]
        count = s["deal_count"]
        raw = s["total_commission"] or 0
        site_clicks = clicks_by_site.get(site, 0)

        if site_clicks > 0:
            est = raw * (site_clicks / max(count, 1)) * DEFAULT_CONVERSION_RATE
        else:
            est = raw * DEFAULT_CTR * DEFAULT_CONVERSION_RATE

        actual = actuals_by_site.get(site)
        if actual:
            lines.append(
                f"  {site.capitalize()}: {count} deals | "
                f"Actual: ${actual['commission']:.2f} | Est: ~${est:.2f}"
            )
        elif s["with_tag"] > 0:
            lines.append(f"  {site.capitalize()}: {count} deals | Est: ~${est:.2f}")
        else:
            lines.append(f"  {site.capitalize()}: {count} deals | No tag configured")

    # Combined totals
    combined = total_actual + funnel_total
    lines.append(f"\n<b>TOTALS:</b>")
    if total_actual > 0:
        lines.append(f"  Actual revenue (API): ${total_actual:.2f}")
    lines.append(f"  Estimated revenue: ~${funnel_total:.2f}")
    lines.append(f"  <b>Combined: ~${combined:.2f}</b>")
    lines.append(f"  Confidence: {confidence}")

    # Data sources
    sources_actual = [s for s in actuals_by_site.keys()] if actuals_by_site else []
    sources_est = [s["site"] for s in (summary or []) if s["site"] not in actuals_by_site]
    if sources_actual:
        lines.append(f"\n  API data from: {', '.join(s.capitalize() for s in sources_actual)}")
    if sources_est:
        lines.append(f"  Estimates for: {', '.join(s.capitalize() for s in sources_est)}")

    lines.append(
        "\nℹ️ <i>Actual data from affiliate network APIs.\n"
        "Estimates use funnel modeling (CTR × conversion rate).</i>"
    )

    return "\n".join(lines)

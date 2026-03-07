"""Affiliate network API polling for real revenue data.

Polls configured affiliate networks (Impact Radius, CJ Affiliate, eBay Partner Network)
to fetch actual click, conversion, and commission data. Results are stored in the
affiliate_actuals table for comparison with estimated revenue.
"""

import logging
from datetime import datetime, timedelta

import requests
from config import (
    IMPACT_ACCOUNT_SID, IMPACT_AUTH_TOKEN,
    CJ_DEVELOPER_KEY, CJ_WEBSITE_ID,
    EBAY_PARTNER_KEY,
)
from database import upsert_affiliate_actual

logger = logging.getLogger("DealBot.AffiliateAPI")

# Map Impact Radius advertiser names to internal site names
_IMPACT_ADVERTISER_MAP = {
    "walmart": "walmart",
    "target": "target",
    "groupon": "groupon",
    "skyscanner": "skyscanner",
}


def poll_impact_radius(days_back=2):
    """Pull action data from Impact Radius API.

    Impact Radius REST API:
    - Auth: Basic auth with AccountSID:AuthToken
    - Endpoint: /Mediapartners/{AccountSID}/Actions
    - Params: ActionDateStart, ActionDateEnd
    - Covers: Walmart, Target, Groupon, Skyscanner
    """
    if not IMPACT_ACCOUNT_SID or not IMPACT_AUTH_TOKEN:
        logger.info("Impact Radius not configured, skipping.")
        return

    end_date = datetime.utcnow().strftime("%Y-%m-%d")
    start_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    url = f"https://api.impact.com/Mediapartners/{IMPACT_ACCOUNT_SID}/Actions"
    params = {
        "ActionDateStart": start_date,
        "ActionDateEnd": end_date,
        "PageSize": 100,
    }

    try:
        response = requests.get(
            url,
            auth=(IMPACT_ACCOUNT_SID, IMPACT_AUTH_TOKEN),
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        # Aggregate by advertiser and date
        aggregated = {}
        for action in data.get("Actions", []):
            advertiser = (action.get("AdvertiserName") or "").lower()
            action_date = action.get("ActionDate", "")[:10]

            # Map to internal site name
            site = None
            for key, name in _IMPACT_ADVERTISER_MAP.items():
                if key in advertiser:
                    site = name
                    break
            if not site:
                continue

            key = (site, action_date)
            if key not in aggregated:
                aggregated[key] = {"clicks": 0, "conversions": 0, "revenue": 0, "commission": 0}

            aggregated[key]["conversions"] += 1
            aggregated[key]["revenue"] += float(action.get("Amount") or 0)
            aggregated[key]["commission"] += float(action.get("Payout") or 0)

        for (site, action_date), agg in aggregated.items():
            upsert_affiliate_actual(
                network="impact",
                site=site,
                action_date=action_date,
                clicks=agg["clicks"],
                conversions=agg["conversions"],
                revenue=agg["revenue"],
                commission=agg["commission"],
            )

        logger.info("Impact Radius: fetched %d action records.", len(data.get("Actions", [])))

    except requests.RequestException as e:
        logger.warning("Impact Radius API error: %s", e)
    except (ValueError, KeyError) as e:
        logger.warning("Impact Radius response parsing error: %s", e)


def poll_cj_affiliate(days_back=2):
    """Pull commission data from CJ Affiliate.

    CJ Commission Detail API:
    - Auth: Authorization header with Personal Access Token
    - Covers: Expedia
    """
    if not CJ_DEVELOPER_KEY or not CJ_WEBSITE_ID:
        logger.info("CJ Affiliate not configured, skipping.")
        return

    end_date = datetime.utcnow().strftime("%Y-%m-%dT23:59:59Z")
    start_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")

    url = "https://commissions.api.cj.com/query"
    headers = {
        "Authorization": f"Bearer {CJ_DEVELOPER_KEY}",
    }
    params = {
        "date-type": "event",
        "start-date": start_date,
        "end-date": end_date,
        "website-id": CJ_WEBSITE_ID,
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        aggregated = {}
        for commission in data.get("commissions", []):
            action_date = (commission.get("eventDate") or "")[:10]
            advertiser = (commission.get("advertiserName") or "").lower()

            site = "expedia" if "expedia" in advertiser else advertiser
            key = (site, action_date)
            if key not in aggregated:
                aggregated[key] = {"clicks": 0, "conversions": 0, "revenue": 0, "commission": 0}

            aggregated[key]["conversions"] += 1
            aggregated[key]["revenue"] += float(commission.get("saleAmount") or 0)
            aggregated[key]["commission"] += float(commission.get("commissionAmount") or 0)

        for (site, action_date), agg in aggregated.items():
            upsert_affiliate_actual(
                network="cj",
                site=site,
                action_date=action_date,
                clicks=agg["clicks"],
                conversions=agg["conversions"],
                revenue=agg["revenue"],
                commission=agg["commission"],
            )

        logger.info("CJ Affiliate: fetched %d commission records.", len(data.get("commissions", [])))

    except requests.RequestException as e:
        logger.warning("CJ Affiliate API error: %s", e)
    except (ValueError, KeyError) as e:
        logger.warning("CJ Affiliate response parsing error: %s", e)


def poll_ebay_partner_network(days_back=2):
    """Pull transaction data from eBay Partner Network.

    eBay Partner Network API:
    - Auth: API key
    - Covers: eBay
    """
    if not EBAY_PARTNER_KEY:
        logger.info("eBay Partner Network not configured, skipping.")
        return

    end_date = datetime.utcnow().strftime("%Y-%m-%d")
    start_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    url = "https://api.ebaypartnernetwork.com/publisher/v2/transaction"
    headers = {
        "Authorization": f"Bearer {EBAY_PARTNER_KEY}",
    }
    params = {
        "start_date": start_date,
        "end_date": end_date,
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        aggregated = {}
        for txn in data.get("transactions", []):
            action_date = (txn.get("transactionDate") or "")[:10]
            key = ("ebay", action_date)
            if key not in aggregated:
                aggregated[key] = {"clicks": 0, "conversions": 0, "revenue": 0, "commission": 0}

            aggregated[key]["conversions"] += 1
            aggregated[key]["revenue"] += float(txn.get("saleAmount") or 0)
            aggregated[key]["commission"] += float(txn.get("earnings") or 0)

        for (site, action_date), agg in aggregated.items():
            upsert_affiliate_actual(
                network="ebay",
                site=site,
                action_date=action_date,
                clicks=agg["clicks"],
                conversions=agg["conversions"],
                revenue=agg["revenue"],
                commission=agg["commission"],
            )

        logger.info("eBay Partner Network: fetched %d transactions.", len(data.get("transactions", [])))

    except requests.RequestException as e:
        logger.warning("eBay Partner Network API error: %s", e)
    except (ValueError, KeyError) as e:
        logger.warning("eBay Partner Network response parsing error: %s", e)


def poll_all_networks(days_back=2):
    """Poll all configured affiliate networks and store results."""
    logger.info("Polling all affiliate networks (last %d days)...", days_back)

    poll_impact_radius(days_back)
    poll_cj_affiliate(days_back)
    poll_ebay_partner_network(days_back)

    logger.info("Affiliate network polling complete.")

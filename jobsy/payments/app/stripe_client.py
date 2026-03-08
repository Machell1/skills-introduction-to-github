"""Stripe integration for Jobsy payments.

Handles:
- Customer creation for payers
- Connect account onboarding for service providers
- Payment intents for service transactions
- Transfers to service provider accounts
- Webhook processing

In development, set STRIPE_SECRET_KEY to a test key (sk_test_...).
"""

import logging
import os
from decimal import Decimal

import stripe

logger = logging.getLogger(__name__)

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
PLATFORM_FEE_PERCENT = Decimal(os.getenv("PLATFORM_FEE_PERCENT", "10"))  # 10% default

stripe.api_key = STRIPE_SECRET_KEY


def is_configured() -> bool:
    return bool(STRIPE_SECRET_KEY)


async def create_customer(email: str, name: str | None = None, metadata: dict | None = None) -> str | None:
    """Create a Stripe Customer for a payer."""
    if not is_configured():
        logger.info("Stripe not configured, skipping customer creation for %s", email)
        return None

    customer = stripe.Customer.create(
        email=email,
        name=name,
        metadata=metadata or {},
    )
    logger.info("Created Stripe customer %s for %s", customer.id, email)
    return customer.id


async def create_connect_account(email: str, country: str = "JM") -> dict | None:
    """Create a Stripe Connect Express account for a service provider.

    Returns dict with account_id and onboarding_url.
    """
    if not is_configured():
        logger.info("Stripe not configured, skipping Connect account for %s", email)
        return None

    account = stripe.Account.create(
        type="express",
        country=country,
        email=email,
        capabilities={
            "card_payments": {"requested": True},
            "transfers": {"requested": True},
        },
    )

    # Generate onboarding link
    link = stripe.AccountLink.create(
        account=account.id,
        refresh_url=os.getenv("STRIPE_REFRESH_URL", "https://jobsy.app/payments/refresh"),
        return_url=os.getenv("STRIPE_RETURN_URL", "https://jobsy.app/payments/complete"),
        type="account_onboarding",
    )

    logger.info("Created Stripe Connect account %s for %s", account.id, email)
    return {
        "account_id": account.id,
        "onboarding_url": link.url,
    }


async def create_payment_intent(
    amount_jmd: Decimal,
    customer_id: str | None,
    connected_account_id: str | None,
    description: str | None = None,
    metadata: dict | None = None,
) -> dict | None:
    """Create a Payment Intent with platform fee.

    Amount is in JMD (Jamaican Dollars). Stripe expects cents.
    """
    if not is_configured():
        logger.info("Stripe not configured, dry-run payment of %s JMD", amount_jmd)
        return None

    amount_cents = int(amount_jmd * 100)
    platform_fee_cents = int(amount_jmd * PLATFORM_FEE_PERCENT / 100 * 100)

    params = {
        "amount": amount_cents,
        "currency": "jmd",
        "description": description,
        "metadata": metadata or {},
    }

    if customer_id:
        params["customer"] = customer_id

    if connected_account_id:
        params["transfer_data"] = {"destination": connected_account_id}
        params["application_fee_amount"] = platform_fee_cents

    intent = stripe.PaymentIntent.create(**params)
    logger.info("Created PaymentIntent %s for %s JMD", intent.id, amount_jmd)

    return {
        "payment_intent_id": intent.id,
        "client_secret": intent.client_secret,
        "amount": amount_jmd,
        "platform_fee": Decimal(platform_fee_cents) / 100,
    }


async def create_payout(account_id: str, amount_jmd: Decimal) -> dict | None:
    """Trigger a payout from a Connect account to their bank."""
    if not is_configured():
        logger.info("Stripe not configured, dry-run payout of %s JMD to %s", amount_jmd, account_id)
        return None

    amount_cents = int(amount_jmd * 100)

    payout = stripe.Payout.create(
        amount=amount_cents,
        currency="jmd",
        stripe_account=account_id,
    )

    logger.info("Created payout %s for %s JMD to account %s", payout.id, amount_jmd, account_id)
    return {"payout_id": payout.id, "status": payout.status}


def verify_webhook_signature(payload: bytes, sig_header: str) -> dict | None:
    """Verify and parse a Stripe webhook event."""
    if not STRIPE_WEBHOOK_SECRET:
        return None

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        return event
    except (stripe.error.SignatureVerificationError, ValueError):
        logger.warning("Invalid Stripe webhook signature")
        return None

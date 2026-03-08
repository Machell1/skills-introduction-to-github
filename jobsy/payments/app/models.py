"""SQLAlchemy ORM models for the payments service.

Supports Stripe for international payments and tracks JMD-based
transactions for the Jamaican marketplace.
"""

from sqlalchemy import Column, DateTime, Index, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB

from shared.database import Base


class PaymentAccount(Base):
    """A user's payment account linking to Stripe Connect."""

    __tablename__ = "payment_accounts"

    id = Column(String, primary_key=True)
    user_id = Column(String, unique=True, nullable=False)
    stripe_account_id = Column(String(100), nullable=True)  # Stripe Connect account
    stripe_customer_id = Column(String(100), nullable=True)  # Stripe Customer
    default_currency = Column(String(3), default="JMD")
    payout_method = Column(String(30), nullable=True)  # bank_transfer, mobile_money
    status = Column(String(20), default="pending")  # pending, active, suspended
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class Transaction(Base):
    """A payment transaction between two users for a service."""

    __tablename__ = "transactions"

    id = Column(String, primary_key=True)
    payer_id = Column(String, nullable=False)
    payee_id = Column(String, nullable=False)
    listing_id = Column(String, nullable=True)
    match_id = Column(String, nullable=True)

    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), default="JMD")
    platform_fee = Column(Numeric(12, 2), default=0)  # Jobsy's cut
    net_amount = Column(Numeric(12, 2), nullable=False)  # payee receives

    stripe_payment_intent_id = Column(String(100), nullable=True)
    stripe_transfer_id = Column(String(100), nullable=True)

    status = Column(String(20), default="pending")
    # pending -> processing -> completed / failed / refunded
    description = Column(String(500), nullable=True)
    metadata = Column(JSONB, default={})

    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_txn_payer", "payer_id", "created_at"),
        Index("idx_txn_payee", "payee_id", "created_at"),
        Index("idx_txn_status", "status"),
    )


class Payout(Base):
    """A payout to a service provider's bank/mobile money account."""

    __tablename__ = "payouts"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), default="JMD")
    stripe_payout_id = Column(String(100), nullable=True)
    status = Column(String(20), default="pending")  # pending, processing, completed, failed
    requested_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

"""
Subscription eligibility derived from the existing `payments_payment` table.

Business rules (no separate subscription table exists):
  - A payment grants access only when its status is "paid" and it is linked
    to a package (plan).
  - Access lasts `package.duration` days from the payment's `created_at`
    (the order time, at most minutes before capture, so the window is never
    longer than what was paid for).
  - "created" (checkout abandoned) and "failed" payments never grant access.
  - Renewals are new paid payments; the latest-expiring one wins.
  - A payment belongs to a customer through `user`, or — for guest checkouts
    where `user` is empty — through a case-insensitive `buyer_email` match.
  - A website with a payment attached uses only that payment; otherwise it
    uses its owner's latest subscription.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from .models import Payment


@dataclass(frozen=True)
class Subscription:
    payment_id: int
    plan: str
    started_at: datetime
    expires_at: datetime

    @property
    def is_active(self):
        return self.expires_at > timezone.now()


def customer_payments(user):
    """Payments that belong to `user`, including guest checkouts made with their email."""
    owned = Q(user=user)
    if user.email:
        owned |= Q(user__isnull=True, buyer_email__iexact=user.email)
    return Payment.objects.filter(owned)


def payment_subscription(payment):
    """The subscription a single payment grants, or None if it grants none."""
    if payment is None or payment.status != "paid" or payment.package is None:
        return None
    return Subscription(
        payment_id=payment.pk,
        plan=payment.package.name,
        started_at=payment.created_at,
        expires_at=payment.created_at + timedelta(days=payment.package.duration),
    )


def latest_subscription(user):
    """The paid subscription with the latest expiry (active or not), or None."""
    payments = (
        customer_payments(user)
        .filter(status="paid", package__isnull=False)
        .select_related("package")
    )

    latest = None
    for payment in payments:
        subscription = payment_subscription(payment)
        if latest is None or subscription.expires_at > latest.expires_at:
            latest = subscription
    return latest


def website_subscription(website):
    """The attached payment's subscription, else the owner's latest one."""
    if website.payment_id:
        return payment_subscription(website.payment)
    return latest_subscription(website.owner)


def active_subscription(user):
    subscription = latest_subscription(user)
    return subscription if subscription and subscription.is_active else None

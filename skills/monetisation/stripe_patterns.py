"""
Monetisation skill: Stripe integration patterns for SaaS.
Injected into MonetisationAgent to produce production-ready billing code.
"""

STRIPE_WEBHOOK_HANDLER = '''
# api/routes/billing.py — Stripe webhook + checkout

import stripe
import os
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from core.database import get_db
from services.subscription_service import SubscriptionService

router = APIRouter(prefix="/billing", tags=["billing"])
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
WEBHOOK_SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]


@router.post("/create-checkout")
async def create_checkout(
    price_id: str,
    user_id: str,
    db: Session = Depends(get_db),
):
    """Create a Stripe Checkout Session for a subscription."""
    service = SubscriptionService(db)
    customer = service.get_or_create_stripe_customer(user_id)

    session = stripe.checkout.Session.create(
        customer=customer.stripe_customer_id,
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{os.environ[\'APP_URL\']}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{os.environ[\'APP_URL\']}/billing/cancelled",
        subscription_data={
            "trial_period_days": 14,
            "metadata": {"user_id": user_id},
        },
        allow_promotion_codes=True,
    )
    return {"checkout_url": session.url, "session_id": session.id}


@router.post("/portal")
async def customer_portal(user_id: str, db: Session = Depends(get_db)):
    """Redirect to Stripe Customer Portal for self-service billing."""
    service = SubscriptionService(db)
    customer = service.get_or_create_stripe_customer(user_id)

    portal = stripe.billing_portal.Session.create(
        customer=customer.stripe_customer_id,
        return_url=f"{os.environ[\'APP_URL\']}/settings/billing",
    )
    return {"portal_url": portal.url}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Handle Stripe webhook events.
    ALL billing state changes come through here — never trust frontend.
    """
    payload = await request.body()
    sig = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid signature")

    service = SubscriptionService(db)
    etype = event["type"]

    # ── Subscription lifecycle ────────────────────────────────────────────────
    if etype == "checkout.session.completed":
        session = event["data"]["object"]
        if session["mode"] == "subscription":
            await service.handle_checkout_complete(session)

    elif etype == "customer.subscription.updated":
        sub = event["data"]["object"]
        await service.handle_subscription_updated(sub)

    elif etype == "customer.subscription.deleted":
        sub = event["data"]["object"]
        await service.handle_subscription_cancelled(sub)

    # ── Payment events ────────────────────────────────────────────────────────
    elif etype == "invoice.payment_succeeded":
        invoice = event["data"]["object"]
        await service.handle_payment_succeeded(invoice)

    elif etype == "invoice.payment_failed":
        invoice = event["data"]["object"]
        await service.handle_payment_failed(invoice)   # triggers dunning email

    # Always return 200 — Stripe retries on non-2xx
    return {"received": True}
'''

SUBSCRIPTION_SERVICE = '''
# services/subscription_service.py

import stripe
from datetime import datetime
from sqlalchemy.orm import Session
from models.subscription import Subscription, SubscriptionStatus
from models.user import User


class SubscriptionService:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_stripe_customer(self, user_id: str):
        user = self.db.get(User, user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        if user.stripe_customer_id:
            return user
        customer = stripe.Customer.create(
            email=user.email,
            name=user.name,
            metadata={"user_id": user_id},
        )
        user.stripe_customer_id = customer.id
        self.db.commit()
        return user

    async def handle_checkout_complete(self, session: dict):
        user_id = session["metadata"].get("user_id") or \\
                  session["subscription_data"]["metadata"]["user_id"]
        sub_data = stripe.Subscription.retrieve(session["subscription"])

        sub = Subscription(
            user_id=user_id,
            stripe_subscription_id=sub_data.id,
            stripe_customer_id=sub_data.customer,
            stripe_price_id=sub_data["items"]["data"][0]["price"]["id"],
            status=SubscriptionStatus.ACTIVE,
            current_period_end=datetime.fromtimestamp(sub_data.current_period_end),
            trial_end=datetime.fromtimestamp(sub_data.trial_end) if sub_data.trial_end else None,
        )
        self.db.add(sub)
        self.db.commit()

    async def handle_subscription_cancelled(self, sub_data: dict):
        sub = self.db.query(Subscription).filter_by(
            stripe_subscription_id=sub_data["id"]
        ).first()
        if sub:
            sub.status = SubscriptionStatus.CANCELLED
            self.db.commit()

    async def handle_payment_failed(self, invoice: dict):
        # Trigger dunning email via your email service
        user_id = self._get_user_id_from_customer(invoice["customer"])
        # send_dunning_email(user_id, invoice["hosted_invoice_url"])
        pass

    def check_entitlement(self, user_id: str, feature: str) -> bool:
        """Check if user has access to a feature based on their plan."""
        sub = self.db.query(Subscription).filter_by(
            user_id=user_id,
            status=SubscriptionStatus.ACTIVE,
        ).first()
        if not sub:
            return False
        return feature in PLAN_FEATURES.get(sub.stripe_price_id, [])

    def _get_user_id_from_customer(self, stripe_customer_id: str) -> str | None:
        user = self.db.query(User).filter_by(
            stripe_customer_id=stripe_customer_id
        ).first()
        return user.id if user else None


# Feature gate per plan
PLAN_FEATURES: dict[str, list[str]] = {
    "price_free":   ["basic_feature"],
    "price_pro":    ["basic_feature", "pro_feature", "api_access"],
    "price_business": ["basic_feature", "pro_feature", "api_access", "team", "sso"],
}
'''

ENTITLEMENT_MIDDLEWARE = '''
# core/entitlements.py — FastAPI dependency for feature gating

from functools import wraps
from fastapi import Depends, HTTPException, status
from core.auth import get_current_user
from core.database import get_db
from services.subscription_service import SubscriptionService
from models.user import User


def require_feature(feature: str):
    """FastAPI dependency that gates a route behind a feature flag."""
    def dependency(
        current_user: User = Depends(get_current_user),
        db = Depends(get_db),
    ):
        service = SubscriptionService(db)
        if not service.check_entitlement(current_user.id, feature):
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "message": f"Feature \'{feature}\' requires an upgrade",
                    "upgrade_url": "/billing/upgrade",
                }
            )
        return current_user
    return Depends(dependency)


# Usage in routes:
# @router.post("/export")
# def export_data(user = require_feature("api_access")):
#     ...
'''

PRICING_TIERS = {
    "free": {
        "name": "Free",
        "price_monthly": 0,
        "price_annually": 0,
        "features": ["Up to 3 projects", "Basic features", "Community support"],
        "cta": "Get started",
        "stripe_price_id_monthly": None,
    },
    "pro": {
        "name": "Pro",
        "price_monthly": 29,
        "price_annually": 290,  # ~2 months free
        "features": [
            "Unlimited projects",
            "All Pro features",
            "API access",
            "Priority support",
            "Custom domain",
        ],
        "cta": "Start 14-day free trial",
        "stripe_price_id_monthly": "price_pro_monthly",
        "stripe_price_id_annually": "price_pro_annual",
        "highlighted": True,
    },
    "business": {
        "name": "Business",
        "price_monthly": 99,
        "price_annually": 990,
        "features": [
            "Everything in Pro",
            "Team collaboration",
            "SSO / SAML",
            "SLA",
            "Dedicated support",
        ],
        "cta": "Contact sales",
        "stripe_price_id_monthly": "price_business_monthly",
    },
}

REVENUE_CAT_MOBILE = '''
// Mobile IAP via RevenueCat (React Native)
// Install: npx expo install react-native-purchases

import Purchases, { PurchasesPackage } from "react-native-purchases";
import { useEffect, useState } from "react";

const REVENUECAT_API_KEY = process.env.EXPO_PUBLIC_REVENUECAT_KEY!;

export function usePaywall() {
  const [packages, setPackages] = useState<PurchasesPackage[]>([]);
  const [isPro, setIsPro] = useState(false);

  useEffect(() => {
    Purchases.configure({ apiKey: REVENUECAT_API_KEY });
    loadOfferings();
    checkEntitlement();
  }, []);

  async function loadOfferings() {
    const offerings = await Purchases.getOfferings();
    if (offerings.current) {
      setPackages(offerings.current.availablePackages);
    }
  }

  async function checkEntitlement() {
    const info = await Purchases.getCustomerInfo();
    setIsPro(info.entitlements.active["pro"] !== undefined);
  }

  async function purchase(pkg: PurchasesPackage) {
    try {
      const { customerInfo } = await Purchases.purchasePackage(pkg);
      setIsPro(customerInfo.entitlements.active["pro"] !== undefined);
      return { success: true };
    } catch (e: any) {
      if (!e.userCancelled) throw e;
      return { success: false, cancelled: true };
    }
  }

  async function restore() {
    const info = await Purchases.restorePurchases();
    setIsPro(info.entitlements.active["pro"] !== undefined);
  }

  return { packages, isPro, purchase, restore };
}
'''

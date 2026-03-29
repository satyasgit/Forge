"""
Monetisation Agent — fully working Stripe + IAP builder.
Pre-scans feature descriptions for billing complexity signals
before calling Claude to produce production Stripe code.
"""
from __future__ import annotations
import re, textwrap
from dataclasses import dataclass
from agents.base import BaseAgent, AgentResult
from skills.monetisation.stripe_patterns import STRIPE_WEBHOOK_HANDLER, SUBSCRIPTION_SERVICE, ENTITLEMENT_MIDDLEWARE, PRICING_TIERS, REVENUE_CAT_MOBILE

@dataclass
class BillingSignal:
    signal_type: str; description: str; what_to_build: str
    def to_summary(self): return f"[{self.signal_type.upper()}] {self.description} → {self.what_to_build}"

from agents.agent_config import register_agent

@register_agent
class MonetisationAgent(BaseAgent):
    name = "monetisation"
    role = "Growth Engineer / Monetisation Specialist"
    enabled_tools = ["write_file"]

    @property
    def system_prompt(self) -> str:
        pricing_text = "\n".join(
            f"  {tier}: ${info['price_monthly']}/mo — {info['features'][0]}"
            for tier, info in PRICING_TIERS.items()
        )
        return textwrap.dedent(f"""
            You are a growth engineer specialising in SaaS and mobile app monetisation.
            You write production-ready Stripe integration code.

            ## Stripe webhook handler template:
            {STRIPE_WEBHOOK_HANDLER}

            ## Subscription service template:
            {SUBSCRIPTION_SERVICE}

            ## Entitlement middleware template:
            {ENTITLEMENT_MIDDLEWARE}

            ## Default pricing tier structure:
            {pricing_text}

            ## Mobile IAP via RevenueCat:
            {REVENUE_CAT_MOBILE}

            ## Output for every task:

            ### PRICING RECOMMENDATION
            Tier structure with rationale. Anchor pricing. Annual discount.

            ### STRIPE SETUP CHECKLIST
            Products, Prices, and webhook endpoint to create in Stripe dashboard.

            ### BACKEND CODE
            - POST /billing/create-checkout
            - POST /billing/portal
            - POST /billing/webhook (all event types handled)
            - GET /billing/status (current plan + period end)
            - Subscription model + migration

            ### ENTITLEMENT SYSTEM
            Feature gates with require_feature() dependency.
            PLAN_FEATURES dict mapping price IDs to feature lists.

            ### MOBILE IAP (if applicable)
            RevenueCat setup + usePaywall hook + Paywall component.

            ### GROWTH MECHANICS
            - Trial strategy (length, what's included)
            - Upgrade prompt placement (where in the app)
            - Dunning email sequence (day 1, 3, 7 after payment failure)
            - Churn prevention (pause vs cancel)

            ### ANALYTICS EVENTS
            Events to track: trial_started, upgrade_clicked, payment_completed, churned.

            ## Non-negotiable:
            - Webhook handler validates Stripe signature on every request
            - All billing state changes come through webhooks (never trust frontend)
            - Entitlement checks on EVERY protected route (use require_feature dependency)
            - Stripe customer created lazily on first checkout (not on signup)
            - Annual plan is 2 months free (16.7% discount)
            - Failed payment triggers dunning email within 1 hour
        """).strip()

    def design_monetisation(self, app_description: str, target_market: str = "", context: str = "") -> AgentResult:
        signals = self._detect_billing_signals(app_description)
        task = textwrap.dedent(f"""
            Design a complete monetisation strategy and Stripe integration for:

            App: {app_description}
            Target market: {target_market or "B2B SaaS, small teams"}
            Context: {context or "Web app + mobile app, no billing currently."}

            Pre-detected billing signals (build all of these):
            {self._format_signals(signals)}

            Produce full monetisation plan + all backend code as described in your instructions.
        """).strip()
        return self.run(task)

    def generate_stripe_integration(self, tier_config: dict | None = None) -> AgentResult:
        tiers_text = str(tier_config) if tier_config else "Use standard Free/Pro/Business tiers."
        task = f"Generate complete production Stripe integration.\nTiers: {tiers_text}\nProduce: webhook handler, subscription service, entitlement middleware, and Stripe setup checklist."
        return self.run(task)

    BILLING_SIGNAL_PATTERNS = [
        (r"\bfree.*(?:trial|plan)|trial\b", "trial", "Build trial start/end webhook handling and dunning flow"),
        (r"\bteam|seat|member|collaborat\b", "team_billing", "Per-seat pricing: quantity on subscription, seat management UI"),
        (r"\busage.?based|metered|per.?api|credit\b", "usage_billing", "Metered billing: Stripe usage records + quota enforcement"),
        (r"\bmobile|ios|android|iap\b", "mobile_iap", "RevenueCat + App Store/Play Store IAP setup"),
        (r"\bannual|yearly|discount\b", "annual_plan", "Annual price ID + 2-month-free calculation + toggle UI"),
        (r"\bchurn|cancel|pause\b", "churn_prevention", "Cancellation flow: pause option, exit survey, win-back email"),
        (r"\brefund|dispute|chargeback\b", "disputes", "Webhook handler for dispute.created, charge.refunded"),
        (r"\bcoupon|discount|promo\b", "promotions", "Stripe coupon creation + allow_promotion_codes in checkout"),
        (r"\benterprise|custom.?pricing|sales\b", "enterprise", "Contact sales flow + custom Stripe price creation"),
    ]

    def _detect_billing_signals(self, text: str) -> list[BillingSignal]:
        signals = []
        for regex, signal_type, what_to_build in self.BILLING_SIGNAL_PATTERNS:
            if re.search(regex, text, re.IGNORECASE):
                match = re.search(regex, text, re.IGNORECASE)
                signals.append(BillingSignal(signal_type, f"Detected: '{match.group(0)}'", what_to_build))
        return signals

    def _format_signals(self, signals: list[BillingSignal]) -> str:
        if not signals: return "No specific billing signals detected — use standard subscription model."
        return "\n".join(["Billing signals:"] + [f"  {s.to_summary()}" for s in signals])

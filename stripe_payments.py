"""
Stripe payment integration for Your Life Your Home platform.
Handles subscription creation, webhook events, and customer portal.
"""
import os
import stripe
from flask import current_app

# Initialize Stripe with secret key from environment
def get_stripe():
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    return stripe

# Subscription tier definitions
SUBSCRIPTION_TIERS = {
    "professional": {
        "name": "Professional",
        "price_monthly": 2900,  # cents = $29.00
        "price_display": "$29/mo",
        "price_env_key": "STRIPE_PROFESSIONAL_PRICE_ID",
        "features": [
            "Unlimited CRM contacts",
            "Unlimited transactions",
            "AI Concierge (lead qualification)",
            "Full Marketing Hub",
            "All Power Tools (CMA, Farming, Scripts)",
            "Seasonal checklists & invoicing",
            "Referral tracking",
            "Priority email support",
            "Partner with subscribed lenders/agents",
        ]
    },
    "elite": {
        "name": "Elite",
        "price_monthly": 7900,  # cents = $79.00
        "price_display": "$79/mo",
        "price_env_key": "STRIPE_ELITE_PRICE_ID",
        "features": [
            "Everything in Professional",
            "Custom branding & white-label concierge",
            "Advanced farming & geo mailers",
            "Featured partner directory listing",
            "Early access to new features",
            "Dedicated onboarding support",
            "Revenue share on referred subscriptions",
            "Multiple team member seats (coming soon)",
        ]
    }
}

def create_checkout_session(user_id, user_email, user_name, tier, role, success_url, cancel_url):
    """
    Create a Stripe Checkout session for a subscription.
    Returns (session_url, error_message)
    """
    s = get_stripe()

    price_env_key = SUBSCRIPTION_TIERS.get(tier, {}).get("price_env_key")
    price_id = os.environ.get(price_env_key, "") if price_env_key else ""

    if not s.api_key:
        return None, "Stripe is not configured yet. Please contact support."

    if not price_id:
        return None, f"Price ID for {tier} plan not configured. Please contact support."

    try:
        session = s.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            customer_email=user_email,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel_url,
            metadata={
                "user_id": str(user_id),
                "role": role,
                "tier": tier,
                "user_name": user_name,
            },
            subscription_data={
                "metadata": {
                    "user_id": str(user_id),
                    "role": role,
                    "tier": tier,
                }
            }
        )
        return session.url, None
    except stripe.error.StripeError as e:
        return None, str(e.user_message)
    except Exception as e:
        return None, f"Payment error: {str(e)}"


def create_customer_portal_session(stripe_customer_id, return_url):
    """
    Create a Stripe Customer Portal session so users can manage their subscription.
    Returns (portal_url, error_message)
    """
    s = get_stripe()

    if not s.api_key:
        return None, "Stripe is not configured."

    try:
        session = s.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=return_url,
        )
        return session.url, None
    except stripe.error.StripeError as e:
        return None, str(e.user_message)
    except Exception as e:
        return None, f"Portal error: {str(e)}"


def handle_checkout_completed(session, db_update_fn):
    """
    Handle a completed checkout session. Extracts metadata and updates user.
    db_update_fn: callable(user_id, tier, stripe_customer_id, stripe_subscription_id)
    """
    metadata = session.get("metadata", {})
    user_id = metadata.get("user_id")
    tier = metadata.get("tier")
    stripe_customer_id = session.get("customer")
    stripe_subscription_id = session.get("subscription")

    if user_id and tier:
        try:
            db_update_fn(int(user_id), tier, stripe_customer_id, stripe_subscription_id)
            return True
        except Exception as e:
            print(f"[Stripe] Error updating user {user_id}: {e}")
            return False
    return False


def handle_subscription_deleted(subscription, db_update_fn):
    """
    Handle a subscription cancellation. Downgrades user to free tier.
    db_update_fn: callable(stripe_subscription_id)
    """
    subscription_id = subscription.get("id")
    if subscription_id:
        try:
            db_update_fn(subscription_id)
            return True
        except Exception as e:
            print(f"[Stripe] Error handling cancellation for {subscription_id}: {e}")
            return False
    return False


def verify_webhook(payload, sig_header):
    """
    Verify Stripe webhook signature.
    Returns (event, error_message)
    """
    s = get_stripe()
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    if not webhook_secret:
        return None, "Webhook secret not configured"

    try:
        event = s.Webhook.construct_event(payload, sig_header, webhook_secret)
        return event, None
    except ValueError:
        return None, "Invalid payload"
    except stripe.error.SignatureVerificationError:
        return None, "Invalid signature"

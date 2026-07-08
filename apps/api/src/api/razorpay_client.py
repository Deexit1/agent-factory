"""T-205 (SPEC-205): sole owner of Razorpay REST API calls (enforced by
scripts/check_razorpay_gate.py, same discipline check_github_app_gate.py already
applies to GitHub and check_llm_router_gate.py applies to LLM provider SDKs) — real
Basic-auth httpx calls to api.razorpay.com, no vendor SDK (this repo's own established
convention: T-202's provider router and T-203's github_app_client.py both hand-roll a
thin httpx wrapper over the vendor's REST API instead of pulling in an SDK, which keeps
the client directly respx-testable at the HTTP boundary).

No live Razorpay account is reachable in this environment (this session's human
explicitly chose Razorpay over Stripe and has no keys for either) — every call here is
exercised in tests via respx HTTP-boundary fault injection, the same precedent as
github_app_client.py, never against a real merchant account.

Platform credentials (RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET/RAZORPAY_WEBHOOK_SECRET) are
env vars only, never persisted to DB/logs/traces — same standing as
GITHUB_APP_WEBHOOK_SECRET (docs/05-security.md).
"""

import hashlib
import hmac
import os
from dataclasses import dataclass

import httpx

_API_BASE = "https://api.razorpay.com/v1"


class RazorpayApiError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        super().__init__(f"Razorpay API error {status_code}: {detail}")


class RazorpayNotConfigured(Exception):
    def __init__(self) -> None:
        super().__init__(
            "Razorpay not configured (RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET) — see "
            "docs/06-tech-stack.md's implementation-status note"
        )


def _credentials() -> tuple[str, str]:
    key_id = os.environ.get("RAZORPAY_KEY_ID", "")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "")
    if not key_id or not key_secret:
        raise RazorpayNotConfigured()
    return key_id, key_secret


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code >= 400:
        raise RazorpayApiError(response.status_code, response.text)


def to_paise(amount_inr: float) -> int:
    """Razorpay amounts are always in the smallest currency unit."""
    return round(amount_inr * 100)


@dataclass(frozen=True)
class RazorpayCustomer:
    id: str


def create_customer(*, name: str, email: str, timeout_s: float = 10.0) -> RazorpayCustomer:
    key_id, key_secret = _credentials()
    with httpx.Client(timeout=timeout_s, auth=(key_id, key_secret)) as client:
        response = client.post(f"{_API_BASE}/customers", json={"name": name, "email": email})
    _raise_for_status(response)
    return RazorpayCustomer(id=response.json()["id"])


@dataclass(frozen=True)
class RazorpaySubscription:
    id: str
    status: str
    short_url: str
    current_end: int | None


def create_subscription(
    *, plan_key: str, customer_id: str, total_count: int = 12, timeout_s: float = 10.0
) -> RazorpaySubscription:
    """`plan_key` (our billing_plans.PLANS key, e.g. "starter") is threaded through as a
    Razorpay subscription `notes` field rather than a pre-created Razorpay Plan id — with
    no live account to register real Plan objects against, this keeps the mechanism
    real and testable without inventing Plan ids that could never be verified."""
    key_id, key_secret = _credentials()
    body = {
        "customer_id": customer_id,
        "total_count": total_count,
        "customer_notify": 1,
        "notes": {"agent_factory_plan": plan_key},
    }
    with httpx.Client(timeout=timeout_s, auth=(key_id, key_secret)) as client:
        response = client.post(f"{_API_BASE}/subscriptions", json=body)
    _raise_for_status(response)
    data = response.json()
    return RazorpaySubscription(
        id=data["id"],
        status=data.get("status", "created"),
        short_url=data.get("short_url", ""),
        current_end=data.get("current_end"),
    )


def fetch_subscription(*, subscription_id: str, timeout_s: float = 10.0) -> RazorpaySubscription:
    key_id, key_secret = _credentials()
    with httpx.Client(timeout=timeout_s, auth=(key_id, key_secret)) as client:
        response = client.get(f"{_API_BASE}/subscriptions/{subscription_id}")
    _raise_for_status(response)
    data = response.json()
    return RazorpaySubscription(
        id=data["id"],
        status=data.get("status", "created"),
        short_url=data.get("short_url", ""),
        current_end=data.get("current_end"),
    )


@dataclass(frozen=True)
class RazorpayAddon:
    id: str


def create_addon(
    *,
    subscription_id: str,
    name: str,
    amount_inr: float,
    currency: str = "INR",
    timeout_s: float = 10.0,
) -> RazorpayAddon:
    """Razorpay's mechanism for a one-off/metered charge added to a subscription's next
    invoice — the closest real analogue to Stripe usage records. This is what the
    nightly metering job (billing_service.run_metering_for_day) calls for any overage."""
    key_id, key_secret = _credentials()
    body = {
        "item": {"name": name, "amount": to_paise(amount_inr), "currency": currency},
    }
    with httpx.Client(timeout=timeout_s, auth=(key_id, key_secret)) as client:
        response = client.post(f"{_API_BASE}/subscriptions/{subscription_id}/addons", json=body)
    _raise_for_status(response)
    return RazorpayAddon(id=response.json()["id"])


def verify_webhook_signature(raw_body: bytes, signature_header: str | None, *, secret: str) -> bool:
    """Razorpay's webhook signature is a raw hex HMAC-SHA256 digest in
    X-Razorpay-Signature (no "sha256=" prefix, unlike GitHub's convention in
    github_app_client.verify_webhook_signature). An unset secret disables verification —
    same local/dev convenience as CI_WEBHOOK_SECRET/GITHUB_APP_WEBHOOK_SECRET."""
    if not secret:
        return True
    if not signature_header:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)

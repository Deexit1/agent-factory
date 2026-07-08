"""T-205 (SPEC-205): real razorpay_client.py HTTP calls, fault-injected at the HTTP
boundary via respx — no live Razorpay account exists in this environment (same T-202
packages/llm_router/test_fallover.py / T-203 test_github_app_client_http.py precedent)."""

import httpx
import pytest
import respx

from api.razorpay_client import (
    RazorpayApiError,
    RazorpayNotConfigured,
    create_addon,
    create_customer,
    create_subscription,
    fetch_subscription,
    to_paise,
    verify_webhook_signature,
)

_BASE = "https://api.razorpay.com/v1"


@pytest.fixture(autouse=True)
def _razorpay_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_fake_key_id")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_test_fake_key_secret")


def test_to_paise_converts_rupees_to_the_smallest_unit() -> None:
    assert to_paise(49.99) == 4_999
    assert to_paise(100) == 10_000


def test_create_customer_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
    with pytest.raises(RazorpayNotConfigured):
        create_customer(name="Acme", email="acme@example.com")


@respx.mock
def test_create_customer_returns_a_real_id() -> None:
    respx.post(f"{_BASE}/customers").mock(
        return_value=httpx.Response(201, json={"id": "cust_fake123"})
    )

    customer = create_customer(name="Acme Inc", email="billing@acme.example.com")

    assert customer.id == "cust_fake123"


@respx.mock
def test_create_subscription_threads_the_plan_key_through_notes() -> None:
    route = respx.post(f"{_BASE}/subscriptions").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": "sub_fake123",
                "status": "created",
                "short_url": "https://rzp.io/i/fake",
                "current_end": 1_800_000_000,
            },
        )
    )

    subscription = create_subscription(plan_key="starter", customer_id="cust_fake123")

    assert subscription.id == "sub_fake123"
    assert subscription.short_url == "https://rzp.io/i/fake"
    sent_body = route.calls.last.request.content
    assert b"agent_factory_plan" in sent_body
    assert b"starter" in sent_body


@respx.mock
def test_fetch_subscription_returns_the_portal_short_url() -> None:
    respx.get(f"{_BASE}/subscriptions/sub_fake123").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "sub_fake123",
                "status": "active",
                "short_url": "https://rzp.io/i/fake",
                "current_end": 1_800_000_000,
            },
        )
    )

    subscription = fetch_subscription(subscription_id="sub_fake123")

    assert subscription.status == "active"
    assert subscription.short_url == "https://rzp.io/i/fake"


@respx.mock
def test_create_addon_returns_a_real_id() -> None:
    respx.post(f"{_BASE}/subscriptions/sub_fake123/addons").mock(
        return_value=httpx.Response(201, json={"id": "addon_fake123"})
    )

    addon = create_addon(subscription_id="sub_fake123", name="overage", amount_inr=250.0)

    assert addon.id == "addon_fake123"


@respx.mock
def test_a_4xx_response_raises_razorpay_api_error() -> None:
    respx.post(f"{_BASE}/customers").mock(
        return_value=httpx.Response(400, json={"error": {"description": "bad request"}})
    )

    with pytest.raises(RazorpayApiError):
        create_customer(name="Acme", email="acme@example.com")


def test_verify_webhook_signature_accepts_a_real_hmac() -> None:
    import hashlib
    import hmac

    secret = "test-razorpay-webhook-secret"
    body = b'{"event":"payment.failed"}'
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert verify_webhook_signature(body, digest, secret=secret)
    assert not verify_webhook_signature(body, "wrong-digest", secret=secret)
    assert not verify_webhook_signature(body, None, secret=secret)


def test_verify_webhook_signature_with_no_secret_disables_verification() -> None:
    """Local/dev convenience — same standing as CI_WEBHOOK_SECRET/
    GITHUB_APP_WEBHOOK_SECRET when unset."""
    assert verify_webhook_signature(b"anything", None, secret="")

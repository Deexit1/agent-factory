import hashlib
import hmac
from datetime import UTC, datetime

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from api.github_app_client import mint_app_jwt, verify_webhook_signature


def _generate_rsa_keypair() -> tuple[str, rsa.RSAPublicKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return pem, private_key.public_key()


def test_verify_webhook_signature_accepts_a_valid_hmac() -> None:
    body = b'{"action":"deleted"}'
    secret = "test-secret"
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert verify_webhook_signature(body, f"sha256={digest}", secret=secret)


def test_verify_webhook_signature_rejects_a_forged_signature() -> None:
    body = b'{"action":"deleted"}'
    assert not verify_webhook_signature(body, "sha256=" + "0" * 64, secret="test-secret")


def test_verify_webhook_signature_rejects_missing_header() -> None:
    assert not verify_webhook_signature(b"{}", None, secret="test-secret")


def test_verify_webhook_signature_disabled_when_secret_unset() -> None:
    # Dev/local convenience, mirrors webhook_service.verify_signature's same rule.
    assert verify_webhook_signature(b"{}", None, secret="")


def test_mint_app_jwt_sets_iat_exp_iss() -> None:
    pem, public_key = _generate_rsa_keypair()

    now = datetime(2026, 7, 8, 12, 0, 0, tzinfo=UTC)
    token = mint_app_jwt(app_id="123456", private_key_pem=pem, now=now)

    # verify_iat/verify_exp off: this test proves OUR claim construction against a
    # fixed, controlled `now`, independent of the real wall clock at test-run time.
    decoded = jwt.decode(
        token,
        public_key,
        algorithms=["RS256"],
        options={"verify_iat": False, "verify_exp": False},
    )

    assert decoded["iss"] == "123456"
    assert decoded["iat"] == int(now.timestamp()) - 60
    assert decoded["exp"] == int(now.timestamp()) + 9 * 60

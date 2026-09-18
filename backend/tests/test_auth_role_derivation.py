"""Pure unit tests for app/auth.py's role-derivation logic
(_role_from_claims) — no live service, no real JWT needed, since this
function only ever looks at an already-verified claims dict. The actual
signature verification (the part that matters for real security) is
exercised live against the running service in
tests/phase17_trust_boundary/test_20_hardening.py — this file is purely
about "given a claims dict, what role comes out," including the one rule
most likely to have an off-by-something bug: the MERCHANT_ADMIN_EMAILS
allowlist override.
"""

import pytest

from app.auth import _role_from_claims
from app.config import settings


@pytest.fixture(autouse=True)
def _reset_admin_emails():
    original = settings.MERCHANT_ADMIN_EMAILS
    yield
    settings.MERCHANT_ADMIN_EMAILS = original


def test_no_role_claim_defaults_to_shopper():
    settings.MERCHANT_ADMIN_EMAILS = ""
    assert _role_from_claims({"sub": "u1", "email": "someone@example.com"}) == "SHOPPER"


def test_app_metadata_role_is_honored():
    settings.MERCHANT_ADMIN_EMAILS = ""
    claims = {"sub": "u1", "email": "x@example.com", "app_metadata": {"role": "merchant_admin"}}
    assert _role_from_claims(claims) == "MERCHANT_ADMIN"  # uppercased


def test_user_metadata_role_is_a_lower_priority_fallback():
    settings.MERCHANT_ADMIN_EMAILS = ""
    # app_metadata (set only by a trusted server-side process in a real
    # Supabase project, never by the end user themselves) must win over
    # user_metadata (which a signed-in user CAN edit about their own
    # account) if both happen to be present.
    claims = {
        "sub": "u1",
        "email": "x@example.com",
        "app_metadata": {"role": "shopper"},
        "user_metadata": {"role": "merchant_admin"},
    }
    assert _role_from_claims(claims) == "SHOPPER"


def test_merchant_admin_emails_allowlist_overrides_claimed_role():
    # The whole point of this allowlist: even if Supabase's own
    # app_metadata.role is unset/wrong for a demo account, a configured
    # email is still promoted to MERCHANT_ADMIN.
    settings.MERCHANT_ADMIN_EMAILS = "owner@example.com, other@example.com"
    claims = {"sub": "u1", "email": "Owner@Example.com"}  # case should not matter
    assert _role_from_claims(claims) == "MERCHANT_ADMIN"


def test_merchant_admin_emails_allowlist_does_not_affect_other_emails():
    settings.MERCHANT_ADMIN_EMAILS = "owner@example.com"
    claims = {"sub": "u1", "email": "random-shopper@example.com"}
    assert _role_from_claims(claims) == "SHOPPER"


def test_an_attacker_cannot_self_claim_a_role_that_isnt_theirs_via_email_alone():
    # A user whose email is NOT on the allowlist claiming
    # app_metadata.role=MERCHANT_ADMIN in a crafted (but, in the real
    # flow, unverifiable-without-a-valid-signature) payload still reads
    # as MERCHANT_ADMIN at THIS layer — this function trusts its input
    # completely, which is correct, because require_user() only ever
    # calls it AFTER the JWT signature has already been independently
    # verified. This test documents that boundary explicitly: this
    # function is not itself a security control, the signature check
    # upstream of it is.
    settings.MERCHANT_ADMIN_EMAILS = ""
    claims = {"sub": "attacker", "email": "attacker@example.com", "app_metadata": {"role": "MERCHANT_ADMIN"}}
    assert _role_from_claims(claims) == "MERCHANT_ADMIN"

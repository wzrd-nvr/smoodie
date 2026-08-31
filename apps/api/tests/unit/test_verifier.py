"""Claim mapping for verified Firebase identities.

The adapter around firebase-admin holds no logic beyond this mapping, which is
why substituting a fake verifier in the integration tests is safe.
"""

from smoodie_api.auth.verifier import _identity_from_claims


def test_prefers_uid_claim() -> None:
    identity = _identity_from_claims({"uid": "from-uid", "sub": "from-sub"})
    assert identity.uid == "from-uid"


def test_falls_back_to_sub_claim() -> None:
    """verify_id_token returns 'uid'; raw JWT payloads only carry 'sub'."""
    assert _identity_from_claims({"sub": "from-sub"}).uid == "from-sub"


def test_maps_optional_profile_claims() -> None:
    identity = _identity_from_claims(
        {"uid": "u", "email": "a@example.com", "email_verified": True, "name": "Angel"}
    )
    assert identity.email == "a@example.com"
    assert identity.email_verified is True
    assert identity.name == "Angel"


def test_missing_optional_claims_are_none_not_errors() -> None:
    identity = _identity_from_claims({"uid": "u"})
    assert identity.email is None
    assert identity.name is None
    assert identity.email_verified is False


def test_email_verified_is_coerced_to_bool() -> None:
    """Firebase has been known to send this as a string."""
    assert _identity_from_claims({"uid": "u", "email_verified": "true"}).email_verified is True
    assert _identity_from_claims({"uid": "u", "email_verified": ""}).email_verified is False

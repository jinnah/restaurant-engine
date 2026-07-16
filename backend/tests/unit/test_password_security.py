"""Password hashing and opaque-token primitives (M2A, ADR-010).

These exercise real Argon2id hashing, so the module keeps the number of
hash computations deliberately small — each one costs real KDF time by
design.
"""

from app.core import security


class TestPasswordHashing:
    def test_roundtrip_and_rejection(self) -> None:
        password_hash = security.hash_password("correct horse battery st!")
        assert security.verify_password(password_hash, "correct horse battery st!")
        assert not security.verify_password(password_hash, "correct horse battery st?")

    def test_explicit_parameters_are_encoded_in_the_hash(self) -> None:
        # The parameter string is part of the stored hash: a silent library
        # default change would surface here immediately.
        password_hash = security.hash_password("correct horse battery st!")
        assert password_hash.startswith("$argon2id$")
        assert (
            f"m={security.ARGON2_MEMORY_COST_KIB}"
            f",t={security.ARGON2_TIME_COST}"
            f",p={security.ARGON2_PARALLELISM}" in password_hash
        )

    def test_fresh_hash_needs_no_rehash(self) -> None:
        assert not security.password_needs_rehash(
            security.hash_password("correct horse battery st!")
        )

    def test_malformed_hash_verifies_false_instead_of_raising(self) -> None:
        assert not security.verify_password("not-an-argon2-hash", "anything")
        assert not security.verify_password("", "anything")

    def test_dummy_verification_never_raises_and_never_matches(self) -> None:
        # Uniform-timing path for unknown/inactive/throttled logins.
        security.verify_dummy_password("any submitted password")
        security.verify_dummy_password("")


class TestOpaqueTokens:
    def test_tokens_are_unique_and_high_entropy(self) -> None:
        tokens = {security.generate_opaque_token() for _ in range(64)}
        assert len(tokens) == 64
        # 32 random bytes URL-safe encoded: 43 characters.
        assert all(len(token) >= 43 for token in tokens)

    def test_token_hash_is_deterministic_sha256_hex(self) -> None:
        token = security.generate_opaque_token()
        first = security.hash_opaque_token(token)
        assert first == security.hash_opaque_token(token)
        assert len(first) == 64
        assert first != token
        assert set(first) <= set("0123456789abcdef")

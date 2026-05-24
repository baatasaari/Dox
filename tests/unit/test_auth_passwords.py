"""Module 4 — Auth: password hashing tests."""
from __future__ import annotations

from common.auth.passwords import hash_password, verify_password


class TestHashPassword:
    def test_returns_string(self) -> None:
        assert isinstance(hash_password("secret"), str)

    def test_hash_differs_from_plain(self) -> None:
        assert hash_password("secret") != "secret"

    def test_hash_starts_with_bcrypt_prefix(self) -> None:
        h = hash_password("secret")
        assert h.startswith("$2b$") or h.startswith("$2a$")

    def test_not_deterministic(self) -> None:
        # bcrypt uses random salt — two hashes of same input must differ
        assert hash_password("secret") != hash_password("secret")

    def test_empty_string_is_hashable(self) -> None:
        h = hash_password("")
        assert isinstance(h, str)
        assert len(h) > 0


class TestVerifyPassword:
    def test_correct_password_returns_true(self) -> None:
        h = hash_password("correct")
        assert verify_password("correct", h) is True

    def test_wrong_password_returns_false(self) -> None:
        h = hash_password("correct")
        assert verify_password("wrong", h) is False

    def test_empty_password_against_hashed_empty(self) -> None:
        h = hash_password("")
        assert verify_password("", h) is True

    def test_empty_password_against_non_empty_hash(self) -> None:
        h = hash_password("nonempty")
        assert verify_password("", h) is False

    def test_different_plain_same_hash_is_false(self) -> None:
        h = hash_password("abc")
        assert verify_password("ABC", h) is False

    def test_multiple_hashes_of_same_plain_all_verify(self) -> None:
        plain = "multihash"
        hashes = [hash_password(plain) for _ in range(3)]
        for h in hashes:
            assert verify_password(plain, h) is True

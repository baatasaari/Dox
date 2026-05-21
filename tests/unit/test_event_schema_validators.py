"""Module 1 — Event Schema: Validator tests."""
from __future__ import annotations

import pytest

from common.schemas.validators import (
    compute_payload_hash,
    validate_schema_version,
    validate_sha256_hash,
    validate_traceparent,
)


class TestValidateSha256Hash:
    def test_valid_64_char_lowercase_hex_passes(self) -> None:
        value = "a" * 64
        assert validate_sha256_hash(value) == value

    def test_none_passes_and_returns_none(self) -> None:
        assert validate_sha256_hash(None) is None

    def test_63_chars_raises(self) -> None:
        with pytest.raises(ValueError, match="64-character"):
            validate_sha256_hash("a" * 63)

    def test_65_chars_raises(self) -> None:
        with pytest.raises(ValueError, match="64-character"):
            validate_sha256_hash("a" * 65)

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_sha256_hash("")

    def test_uppercase_hex_raises(self) -> None:
        # Must be lowercase — uppercase chars fail the pattern
        with pytest.raises(ValueError, match="64-character"):
            validate_sha256_hash("A" * 64)

    def test_non_hex_character_raises(self) -> None:
        # 'g' is not a valid hex character
        with pytest.raises(ValueError):
            validate_sha256_hash("g" * 64)

    def test_mixed_case_raises(self) -> None:
        value = "a" * 32 + "A" * 32
        with pytest.raises(ValueError):
            validate_sha256_hash(value)

    def test_real_sha256_hex_passes(self) -> None:
        real = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert validate_sha256_hash(real) == real


class TestValidateTraceparent:
    VALID = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

    def test_valid_traceparent_passes(self) -> None:
        assert validate_traceparent(self.VALID) == self.VALID

    def test_none_passes_and_returns_none(self) -> None:
        assert validate_traceparent(None) is None

    def test_wrong_version_prefix_raises(self) -> None:
        # Only version "00" is accepted per W3C spec
        bad = "01-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        with pytest.raises(ValueError, match="W3C traceparent"):
            validate_traceparent(bad)

    def test_short_trace_id_raises(self) -> None:
        # trace-id must be 32 hex chars; here it's 30
        bad = "00-4bf92f3577b34da6a3ce929d0e0e47-00f067aa0ba902b7-01"
        with pytest.raises(ValueError):
            validate_traceparent(bad)

    def test_short_parent_id_raises(self) -> None:
        # parent-id must be 16 hex chars; here it's 14
        bad = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902-01"
        with pytest.raises(ValueError):
            validate_traceparent(bad)

    def test_missing_flags_raises(self) -> None:
        bad = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7"
        with pytest.raises(ValueError):
            validate_traceparent(bad)

    def test_arbitrary_string_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_traceparent("not-a-traceparent")

    def test_uppercase_trace_id_raises(self) -> None:
        bad = "00-4BF92F3577B34DA6A3CE929D0E0E4736-00f067aa0ba902b7-01"
        with pytest.raises(ValueError):
            validate_traceparent(bad)


class TestValidateSchemaVersion:
    def test_1_0_passes(self) -> None:
        assert validate_schema_version("1.0") == "1.0"

    def test_2_0_passes(self) -> None:
        assert validate_schema_version("2.0") == "2.0"

    def test_multi_digit_minor_passes(self) -> None:
        assert validate_schema_version("1.10") == "1.10"

    def test_multi_digit_major_passes(self) -> None:
        assert validate_schema_version("10.5") == "10.5"

    def test_bare_integer_raises(self) -> None:
        with pytest.raises(ValueError, match="MAJOR.MINOR"):
            validate_schema_version("1")

    def test_three_part_semver_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_schema_version("1.0.0")

    def test_v_prefix_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_schema_version("v1.0")

    def test_dash_separator_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_schema_version("1-0")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_schema_version("")

    def test_alpha_string_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_schema_version("abc")


class TestComputePayloadHash:
    def test_returns_64_char_lowercase_hex(self) -> None:
        result = compute_payload_hash({"key": "value"})
        assert len(result) == 64
        assert result == result.lower()
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic_on_repeated_calls(self) -> None:
        payload = {"b": 2, "a": 1, "c": [1, 2, 3]}
        assert compute_payload_hash(payload) == compute_payload_hash(payload)

    def test_key_order_does_not_affect_hash(self) -> None:
        a = {"b": 2, "a": 1}
        b = {"a": 1, "b": 2}
        assert compute_payload_hash(a) == compute_payload_hash(b)

    def test_different_payloads_produce_different_hashes(self) -> None:
        assert compute_payload_hash({"a": 1}) != compute_payload_hash({"a": 2})

    def test_empty_dict_is_hashable(self) -> None:
        result = compute_payload_hash({})
        assert len(result) == 64

    def test_nested_payload_is_hashable(self) -> None:
        payload = {"outer": {"inner": [1, 2, 3]}, "flag": True}
        result = compute_payload_hash(payload)
        assert len(result) == 64

    def test_hash_matches_known_sha256(self) -> None:
        # SHA-256 of '{}' (empty JSON with no spaces, sorted)
        import hashlib
        expected = hashlib.sha256(b"{}").hexdigest()
        assert compute_payload_hash({}) == expected

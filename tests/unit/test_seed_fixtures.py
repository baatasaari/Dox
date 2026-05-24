"""Tests for seed fixture helpers."""
from __future__ import annotations

from scripts.seed_fixtures import _demo_user_specs, _policy_files


class TestSeedFixtureHelpers:
    def test_policy_files_returns_yaml_paths(self) -> None:
        files = _policy_files()
        assert all(f.suffix == ".yaml" for f in files)
        assert len(files) >= 2

    def test_policy_files_are_sorted(self) -> None:
        files = _policy_files()
        assert files == sorted(files)

    def test_demo_user_specs_returns_four_users(self) -> None:
        specs = _demo_user_specs("acme")
        assert len(specs) == 4

    def test_demo_user_specs_have_correct_roles(self) -> None:
        specs = _demo_user_specs("acme")
        roles = {s["role"] for s in specs}
        assert roles == {"admin", "operator", "viewer", "agent"}

    def test_demo_user_specs_use_tenant_in_email(self) -> None:
        specs = _demo_user_specs("mycorp")
        assert all("mycorp" in s["email"] for s in specs)

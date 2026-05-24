"""Tests for common/policy_config.py — YAML policy loader."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from common.policy_config import (
    PolicyConfigEntry,
    PolicyConfigFile,
    load_for_tenant,
    load_from_file,
)
from common.schemas.enums import InterventionAction, SentinelType, Severity
from common.schemas.sentinel import PolicyCreate

_CONFIG_DIR = Path(__file__).parent.parent.parent / "config" / "policies"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_ENTRY: dict[str, Any] = {
    "name": "Test Policy",
    "description": "A test policy.",
    "sentinel_type": "tool_misuse",
    "severity": "medium",
    "action": "warn",
    "config": {"key": "value"},
}

_VALID_FILE: dict[str, Any] = {
    "policies": [
        {
            "name": "Policy Alpha",
            "sentinel_type": "injection",
            "severity": "critical",
            "action": "terminate_execution",
            "config": {},
        },
        {
            "name": "Policy Beta",
            "sentinel_type": "trajectory",
            "severity": "high",
            "action": "request_human_review",
            "config": {},
        },
    ]
}


def _write_yaml(tmp_path: Path, data: Any) -> Path:
    p = tmp_path / "policies.yaml"
    p.write_text(yaml.dump(data))
    return p


def _minimal_entry(name: str = "My Policy") -> dict[str, Any]:
    return {
        "name": name,
        "sentinel_type": "cost_loop",
        "severity": "high",
        "action": "pause_agent",
    }


# ---------------------------------------------------------------------------
# TestPolicyConfigEntry
# ---------------------------------------------------------------------------


class TestPolicyConfigEntry:
    def test_valid_entry_parses(self) -> None:
        entry = PolicyConfigEntry.model_validate(_VALID_ENTRY)
        assert entry.name == "Test Policy"
        assert entry.sentinel_type == SentinelType.tool_misuse
        assert entry.severity == Severity.medium
        assert entry.action == InterventionAction.warn
        assert entry.config == {"key": "value"}

    def test_description_defaults_to_empty(self) -> None:
        # description omitted entirely from the minimal entry dict
        entry = PolicyConfigEntry.model_validate(_minimal_entry())
        assert entry.description == ""

    def test_config_defaults_to_empty_dict(self) -> None:
        entry = PolicyConfigEntry.model_validate(_minimal_entry())
        assert entry.config == {}

    def test_invalid_sentinel_type_raises(self) -> None:
        data = {**_VALID_ENTRY, "sentinel_type": "unknown_type"}
        with pytest.raises(ValidationError):
            PolicyConfigEntry.model_validate(data)

    def test_invalid_severity_raises(self) -> None:
        data = {**_VALID_ENTRY, "severity": "extreme"}
        with pytest.raises(ValidationError):
            PolicyConfigEntry.model_validate(data)

    def test_invalid_action_raises(self) -> None:
        data = {**_VALID_ENTRY, "action": "do_nothing"}
        with pytest.raises(ValidationError):
            PolicyConfigEntry.model_validate(data)

    def test_extra_fields_forbidden(self) -> None:
        data = {**_VALID_ENTRY, "unexpected_field": "oops"}
        with pytest.raises(ValidationError):
            PolicyConfigEntry.model_validate(data)


# ---------------------------------------------------------------------------
# TestPolicyConfigFile
# ---------------------------------------------------------------------------


class TestPolicyConfigFile:
    def test_valid_file_parses(self) -> None:
        cfg = PolicyConfigFile.model_validate(_VALID_FILE)
        assert len(cfg.policies) == 2
        assert cfg.policies[0].name == "Policy Alpha"
        assert cfg.policies[1].name == "Policy Beta"

    def test_empty_policies_list(self) -> None:
        cfg = PolicyConfigFile.model_validate({"policies": []})
        assert cfg.policies == []

    def test_duplicate_names_raises(self) -> None:
        data = {
            "policies": [
                _minimal_entry("Duplicate"),
                _minimal_entry("Duplicate"),
            ]
        }
        with pytest.raises(ValidationError, match="Duplicate policy names"):
            PolicyConfigFile.model_validate(data)

    def test_null_document_via_empty_policies(self) -> None:
        # PolicyConfigFile with no 'policies' key uses the default_factory → empty list
        cfg = PolicyConfigFile.model_validate({})
        assert cfg.policies == []


# ---------------------------------------------------------------------------
# TestLoadFromFile
# ---------------------------------------------------------------------------


class TestLoadFromFile:
    def test_load_returns_policy_entries(self, tmp_path: Path) -> None:
        data = {"policies": [_minimal_entry("P1"), _minimal_entry("P2")]}
        path = _write_yaml(tmp_path, data)
        entries = load_from_file(path)
        assert all(isinstance(e, PolicyConfigEntry) for e in entries)

    def test_load_correct_count(self, tmp_path: Path) -> None:
        data = {
            "policies": [_minimal_entry("P1"), _minimal_entry("P2"), _minimal_entry("P3")]
        }
        path = _write_yaml(tmp_path, data)
        entries = load_from_file(path)
        assert len(entries) == 3

    def test_load_empty_yaml_returns_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.yaml"
        p.write_text("")
        entries = load_from_file(p)
        assert entries == []

    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_from_file(tmp_path / "nonexistent.yaml")

    def test_load_invalid_yaml_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text(":\n  :")
        with pytest.raises((yaml.YAMLError, ValueError)):
            load_from_file(p)

    def test_load_invalid_sentinel_type_raises(self, tmp_path: Path) -> None:
        entry = {**_minimal_entry("Bad Sentinel"), "sentinel_type": "unknown_type"}
        path = _write_yaml(tmp_path, {"policies": [entry]})
        with pytest.raises(ValidationError):
            load_from_file(path)

    def test_load_missing_required_field_raises(self, tmp_path: Path) -> None:
        # 'name' is required
        entry = {
            "sentinel_type": "cost_loop",
            "severity": "high",
            "action": "pause_agent",
        }
        path = _write_yaml(tmp_path, {"policies": [entry]})
        with pytest.raises(ValidationError):
            load_from_file(path)

    def test_load_duplicate_names_raises(self, tmp_path: Path) -> None:
        data = {"policies": [_minimal_entry("Same"), _minimal_entry("Same")]}
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValidationError, match="Duplicate policy names"):
            load_from_file(path)


# ---------------------------------------------------------------------------
# TestLoadForTenant
# ---------------------------------------------------------------------------


class TestLoadForTenant:
    def test_returns_policy_create_instances(self, tmp_path: Path) -> None:
        data = {"policies": [_minimal_entry("PC1")]}
        path = _write_yaml(tmp_path, data)
        creates = load_for_tenant(path, "tenant-abc")
        assert all(isinstance(c, PolicyCreate) for c in creates)

    def test_tenant_id_injected(self, tmp_path: Path) -> None:
        data = {"policies": [_minimal_entry("PC2"), _minimal_entry("PC3")]}
        path = _write_yaml(tmp_path, data)
        creates = load_for_tenant(path, "my-tenant")
        assert all(c.tenant_id == "my-tenant" for c in creates)

    def test_count_matches_yaml(self, tmp_path: Path) -> None:
        data = {
            "policies": [_minimal_entry("T1"), _minimal_entry("T2"), _minimal_entry("T3")]
        }
        path = _write_yaml(tmp_path, data)
        creates = load_for_tenant(path, "t")
        assert len(creates) == 3

    def test_all_fields_preserved(self, tmp_path: Path) -> None:
        entry: dict[str, Any] = {
            "name": "Full Policy",
            "description": "Detailed description.",
            "sentinel_type": "injection",
            "severity": "critical",
            "action": "terminate_execution",
            "config": {"strict": True, "threshold": 0.9},
        }
        path = _write_yaml(tmp_path, {"policies": [entry]})
        creates = load_for_tenant(path, "corp")
        pc = creates[0]
        assert pc.name == "Full Policy"
        assert pc.description == "Detailed description."
        assert pc.sentinel_type == SentinelType.injection
        assert pc.severity == Severity.critical
        assert pc.action == InterventionAction.terminate_execution
        assert pc.config == {"strict": True, "threshold": 0.9}


# ---------------------------------------------------------------------------
# TestRealConfigFiles
# ---------------------------------------------------------------------------


class TestRealConfigFiles:
    def test_default_governance_loads(self) -> None:
        entries = load_from_file(_CONFIG_DIR / "default_governance.yaml")
        assert len(entries) == 5

    def test_strict_security_loads(self) -> None:
        entries = load_from_file(_CONFIG_DIR / "strict_security.yaml")
        assert len(entries) == 3

    def test_all_policies_have_unique_names_across_files(self) -> None:
        all_policies = []
        for f in sorted(_CONFIG_DIR.glob("*.yaml")):
            all_policies.extend(load_from_file(f))
        names = [p.name for p in all_policies]
        assert len(names) == len(set(names)), "Policy names must be globally unique"

"""YAML-based policy configuration loader for Dox."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator

from common.schemas.enums import InterventionAction, SentinelType, Severity
from common.schemas.sentinel import PolicyCreate


class PolicyConfigEntry(BaseModel):
    """Single policy definition as it appears in a YAML config file."""

    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    sentinel_type: SentinelType
    severity: Severity
    action: InterventionAction
    config: dict[str, Any] = Field(default_factory=dict)


class PolicyConfigFile(BaseModel):
    """Root schema for a policy YAML file."""

    model_config = {"extra": "forbid"}

    policies: list[PolicyConfigEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _names_unique(self) -> PolicyConfigFile:
        names = [p.name for p in self.policies]
        if len(names) != len(set(names)):
            duplicates = {n for n in names if names.count(n) > 1}
            raise ValueError(f"Duplicate policy names: {duplicates}")
        return self


def load_from_file(path: str | Path) -> list[PolicyConfigEntry]:
    """Load and validate policies from a YAML file.

    Returns an empty list for a null/empty YAML document.
    Raises FileNotFoundError if the path does not exist.
    Raises pydantic.ValidationError for schema violations.
    Raises yaml.YAMLError for malformed YAML.
    """
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    if raw is None:
        return []
    config_file = PolicyConfigFile.model_validate(raw)
    return config_file.policies


def load_for_tenant(path: str | Path, tenant_id: str) -> list[PolicyCreate]:
    """Load policies from a YAML file and return PolicyCreate objects for a tenant."""
    entries = load_from_file(path)
    return [
        PolicyCreate(
            tenant_id=tenant_id,
            name=entry.name,
            description=entry.description,
            sentinel_type=entry.sentinel_type,
            severity=entry.severity,
            action=entry.action,
            config=entry.config,
        )
        for entry in entries
    ]

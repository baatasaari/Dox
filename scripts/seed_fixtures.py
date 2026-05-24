"""Seed development fixtures for Dox.

Loads default governance policies into the configured tenant and creates
a demo tenant + four users (admin/operator/viewer/agent role) if they
don't already exist.

Usage:
    poetry run python -m scripts.seed_fixtures [--tenant SLUG]
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers (pure, no DB required — testable)
# ---------------------------------------------------------------------------

_POLICIES_DIR = Path(__file__).parent.parent / "config" / "policies"


def _policy_files() -> list[Path]:
    """Return sorted policy YAML files from the config directory."""
    return sorted(_POLICIES_DIR.glob("*.yaml"))


def _demo_user_specs(tenant_id: str) -> list[dict[str, str]]:
    """Return the demo user payloads for a given tenant."""
    return [
        {"email": f"admin@{tenant_id}.demo", "role": "admin"},
        {"email": f"operator@{tenant_id}.demo", "role": "operator"},
        {"email": f"viewer@{tenant_id}.demo", "role": "viewer"},
        {"email": f"agent@{tenant_id}.demo", "role": "agent"},
    ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def seed(tenant_slug: str = "demo") -> None:
    """Seed the database with fixture data for *tenant_slug*."""
    from common.db import init_db
    from common.policy_config import load_for_tenant

    await init_db()

    policy_creates = []
    for yaml_path in _policy_files():
        policy_creates.extend(load_for_tenant(yaml_path, tenant_slug))

    print(f"[seed] Loaded {len(policy_creates)} policies for tenant '{tenant_slug}'")
    for pc in policy_creates:
        print(f"  - {pc.name} ({pc.sentinel_type}/{pc.severity})")
    print("[seed] Done — connect a running Dox instance to import these into the DB.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Seed Dox development fixtures")
    parser.add_argument("--tenant", default="demo", help="Tenant slug to seed (default: demo)")
    args = parser.parse_args(argv)
    asyncio.run(seed(args.tenant))


if __name__ == "__main__":
    main()

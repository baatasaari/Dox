"""Root conftest — set required env vars before any test module is imported."""
from __future__ import annotations

import os

os.environ.setdefault("DOX_DATABASE__URL", "postgresql+asyncpg://test:test@localhost/dox_test")
os.environ.setdefault("DOX_SECRET_KEY", "test-secret-key-for-unit-tests-only")

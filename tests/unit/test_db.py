"""Module 3 — DB: connection initialisation tests."""
from __future__ import annotations

import pytest

import common.db as db_module
from common.db import get_session


class TestGetSession:
    async def test_get_session_raises_when_not_initialised(self) -> None:
        original = db_module._session_factory
        db_module._session_factory = None
        try:
            gen = get_session()
            with pytest.raises(RuntimeError, match="not initialised"):
                await gen.__anext__()
        finally:
            db_module._session_factory = original

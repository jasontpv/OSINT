"""Pytest configuration and fixtures for async test support."""

import pytest
import asyncio

# Ensure pytest-asyncio is loaded
pytest_plugins = ("pytest_asyncio",)


@pytest.fixture(autouse=True)
def event_loop_policy():
    """Set the event loop policy for tests."""
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

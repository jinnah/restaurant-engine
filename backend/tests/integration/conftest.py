"""Integration fixtures: real PostgreSQL required (ADR-005).

All tests under tests/integration/ carry the ``integration`` marker and run
against the Docker Compose development server. A missing database is a hard,
explained failure — never a silent skip — so the suite cannot go green while
silently not testing the database. The shared ``test_database_url`` fixture
lives in the root conftest (tests/security/ needs it too, from M2A).
"""

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/integration" in str(item.path).replace("\\", "/"):
            item.add_marker(pytest.mark.integration)

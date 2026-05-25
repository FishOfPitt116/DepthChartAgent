import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: tests that hit real external APIs (deselected by default)"
    )

import os
import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_LEGACY_REMOTE_TESTS") == "1":
        return
    for item in items:
        path = str(item.fspath)
        if path.endswith("backend_test.py") or path.endswith("test_new_endpoints.py"):
            item.add_marker(pytest.mark.skip(reason="Legacy tests call a shared remote preview and are disabled by default"))

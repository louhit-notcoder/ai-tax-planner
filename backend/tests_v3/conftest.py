"""Test environment is established before application modules are imported.

This prevents module collection order from changing cached security settings.
"""
from __future__ import annotations

import os
from pathlib import Path

DB = Path("/tmp/green_papaya_v3_test.db")
os.environ.setdefault("GREEN_PAPAYA_ENV", "development")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{DB}")
os.environ.setdefault("REQUIRE_MFA_FOR_PRIVILEGED_ROLES", "false")
os.environ.setdefault("ALLOW_DEV_BOOTSTRAP", "true")
os.environ.setdefault("LOCAL_STORAGE_ROOT", "/tmp/gp-v3-storage")
os.environ.setdefault("MALWARE_SCAN_REQUIRED", "false")
os.environ.setdefault("RATE_LIMIT_BACKEND", "memory")
os.environ.setdefault("EMBEDDING_BASE_URL", "")
os.environ.setdefault("EMBEDDING_API_KEY", "")
os.environ.setdefault("EMBEDDING_MODEL", "")

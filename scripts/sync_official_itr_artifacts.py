#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings
from app.itr.schema_registry import OfficialSchemaRegistry


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and pin official AY 2026-27 ITR schemas")
    parser.add_argument("--itr1-url")
    parser.add_argument("--itr2-url")
    parser.add_argument("--version", default="AY2026_27_V1.1")
    args = parser.parse_args()
    settings = get_settings()
    registry = OfficialSchemaRegistry()
    urls = {
        "ITR_1": args.itr1_url or settings.official_itr1_schema_url,
        "ITR_2": args.itr2_url or settings.official_itr2_schema_url,
    }
    for form, url in urls.items():
        artifact = registry.sync(form, url, args.version)
        print(f"Pinned {form}: {artifact.path} sha256={artifact.sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

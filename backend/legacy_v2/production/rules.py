from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from .hashing import sha256_json


RULES_ROOT = Path(__file__).resolve().parents[1] / "rules" / "releases"


def _decimalise(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _decimalise(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decimalise(v) for v in value]
    if isinstance(value, str):
        if value == "INF":
            return Decimal("Infinity")
        try:
            return Decimal(value)
        except Exception:
            return value
    return value


def load_rule_release(release_id: str = "AY2026_27_v1.0.0") -> dict:
    path = RULES_ROOT / f"{release_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Unknown tax rule release: {release_id}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["rule_bundle_hash"] = sha256_json(raw)
    return _decimalise(raw)

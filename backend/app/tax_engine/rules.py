from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2] / "rules" / "releases"


def _convert(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _convert(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_convert(item) for item in value]
    if isinstance(value, str):
        if value == "Infinity":
            return Decimal("Infinity")
        try:
            if any(ch.isdigit() for ch in value) and all(ch in "0123456789.-" for ch in value):
                return Decimal(value)
        except Exception:
            pass
    return value


@lru_cache(maxsize=16)
def load_rule_release(release_id: str = "AY2026_27_V3.0.0") -> dict:
    path = ROOT / f"{release_id}.json"
    if not path.exists():
        raise ValueError(f"Unknown tax rule release: {release_id}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
    raw["rule_bundle_hash"] = hashlib.sha256(canonical).hexdigest()
    return _convert(raw)


load_rules = load_rule_release

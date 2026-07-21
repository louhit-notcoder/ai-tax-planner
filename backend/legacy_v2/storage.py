"""Pluggable object storage wrapper.

Use STORAGE_BACKEND=local for development and STORAGE_BACKEND=emergent for the
existing hosted integration. Production should replace this with an approved,
encrypted S3-compatible implementation and private network policy.
"""
from __future__ import annotations

import os
from pathlib import Path

import requests

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "green-papaya"
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local").lower()
LOCAL_STORAGE_ROOT = Path(os.environ.get("LOCAL_STORAGE_ROOT", Path(__file__).parent / ".local_storage")).resolve()

_storage_key = None

MIME_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp", "pdf": "application/pdf",
    "json": "application/json", "csv": "text/csv", "txt": "text/plain",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _safe_local_path(path: str) -> Path:
    target = (LOCAL_STORAGE_ROOT / path).resolve()
    if LOCAL_STORAGE_ROOT not in target.parents and target != LOCAL_STORAGE_ROOT:
        raise ValueError("Unsafe storage path")
    return target


def init_storage():
    global _storage_key
    if STORAGE_BACKEND == "local":
        LOCAL_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
        return "local"
    if STORAGE_BACKEND != "emergent":
        raise RuntimeError(f"Unsupported STORAGE_BACKEND={STORAGE_BACKEND}")
    if not EMERGENT_KEY:
        raise RuntimeError("EMERGENT_LLM_KEY is required for emergent storage")
    if _storage_key:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    if STORAGE_BACKEND == "local":
        target = _safe_local_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        (target.with_suffix(target.suffix + ".content_type")).write_text(content_type, encoding="utf-8")
        return {"path": path, "size": len(data), "backend": "local"}
    key = init_storage()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def get_object(path: str):
    if STORAGE_BACKEND == "local":
        target = _safe_local_path(path)
        ctype_path = target.with_suffix(target.suffix + ".content_type")
        content_type = ctype_path.read_text(encoding="utf-8") if ctype_path.exists() else "application/octet-stream"
        return target.read_bytes(), content_type
    key = init_storage()
    resp = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key}, timeout=60,
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

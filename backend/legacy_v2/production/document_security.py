from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

from fastapi import HTTPException


ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "json", "txt", "csv", "xlsx"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "application/json",
    "text/plain",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))


@dataclass(frozen=True)
class FileInspection:
    sha256: str
    size: int
    detected_kind: str


def _magic_kind(data: bytes) -> str:
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"PK\x03\x04"):
        return "zip_container"
    stripped = data.lstrip()
    if stripped.startswith((b"{", b"[")):
        return "json_or_text"
    return "text_or_unknown"


def inspect_upload(filename: str, content_type: str, data: bytes) -> FileInspection:
    if not data:
        raise HTTPException(status_code=400, detail="Empty files are not accepted")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_BYTES} byte limit")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Unsupported file extension: {ext or 'none'}")
    if content_type and content_type not in ALLOWED_MIME_TYPES and content_type != "application/octet-stream":
        raise HTTPException(status_code=415, detail=f"Unsupported content type: {content_type}")

    kind = _magic_kind(data)
    if ext == "pdf" and kind != "pdf":
        raise HTTPException(status_code=400, detail="File extension is PDF but signature is not PDF")
    if ext in {"png"} and kind != "png":
        raise HTTPException(status_code=400, detail="File signature does not match PNG")
    if ext in {"jpg", "jpeg"} and kind != "jpeg":
        raise HTTPException(status_code=400, detail="File signature does not match JPEG")
    return FileInspection(sha256=hashlib.sha256(data).hexdigest(), size=len(data), detected_kind=kind)

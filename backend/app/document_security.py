from __future__ import annotations

import hashlib
import io
import os
import socket
import struct
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import fitz
from fastapi import HTTPException

from .config import get_settings

ALLOWED = {
    "pdf": {"application/pdf"},
    "png": {"image/png"},
    "jpg": {"image/jpeg"},
    "jpeg": {"image/jpeg"},
    "json": {"application/json", "text/json", "text/plain"},
    "csv": {"text/csv", "application/csv", "application/vnd.ms-excel", "text/plain"},
    "xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/octet-stream"},
}


@dataclass(frozen=True)
class InspectionResult:
    sha256: str
    size_bytes: int
    extension: str
    detected_kind: str
    password_protected: bool
    malware_scan: str


def _kind(data: bytes) -> str:
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"PK\x03\x04"):
        return "zip"
    stripped = data.lstrip()
    if stripped.startswith((b"{", b"[")):
        return "json"
    return "text"


def _scan_via_clamd(data: bytes, host: str, port: int) -> str:
    try:
        with socket.create_connection((host, port), timeout=10) as connection:
            connection.settimeout(60)
            connection.sendall(b"zINSTREAM\x00")
            for offset in range(0, len(data), 64 * 1024):
                chunk = data[offset:offset + 64 * 1024]
                connection.sendall(struct.pack("!I", len(chunk)))
                connection.sendall(chunk)
            connection.sendall(struct.pack("!I", 0))
            response = bytearray()
            while True:
                part = connection.recv(4096)
                if not part:
                    break
                response.extend(part)
                if b"\x00" in part or b"\n" in part:
                    break
    except (OSError, socket.timeout) as exc:
        raise RuntimeError("ClamAV daemon unavailable") from exc
    result = bytes(response).decode("utf-8", errors="replace").strip("\x00\r\n ")
    if result.endswith("OK"):
        return "CLEAN"
    if "FOUND" in result:
        raise HTTPException(status_code=422, detail="File rejected by malware scanner")
    raise RuntimeError(f"Unexpected ClamAV response: {result[:200]}")


def _scan_malware(data: bytes, filename: str) -> str:
    settings = get_settings()
    command = os.getenv("CLAMSCAN_PATH", "").strip()
    required = settings.malware_scan_required
    if settings.clamd_host:
        try:
            return _scan_via_clamd(data, settings.clamd_host, settings.clamd_port)
        except HTTPException:
            raise
        except RuntimeError as exc:
            if required:
                raise HTTPException(status_code=503, detail="Malware scanner unavailable") from exc
            return "UNAVAILABLE"
    if not command:
        if required:
            raise HTTPException(status_code=503, detail="Malware scanner is required but not configured")
        return "NOT_CONFIGURED"
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / Path(filename).name
        path.write_bytes(data)
        try:
            process = subprocess.run([command, "--no-summary", str(path)], capture_output=True, text=True, timeout=60, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            if required:
                raise HTTPException(status_code=503, detail="Malware scanner unavailable") from exc
            return "UNAVAILABLE"
        if process.returncode == 1:
            raise HTTPException(status_code=422, detail="File rejected by malware scanner")
        if process.returncode != 0:
            if required:
                raise HTTPException(status_code=503, detail="Malware scanner returned an error")
            return "ERROR"
        return "CLEAN"


def inspect_document(filename: str, content_type: str, data: bytes) -> InspectionResult:
    settings = get_settings()
    if not data:
        raise HTTPException(status_code=400, detail="Empty document")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"Document exceeds {settings.max_upload_bytes} bytes")
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED:
        raise HTTPException(status_code=415, detail="Unsupported document type")
    if content_type and content_type not in ALLOWED[extension] and content_type != "application/octet-stream":
        raise HTTPException(status_code=415, detail=f"Unexpected content type for .{extension}")
    kind = _kind(data)
    expected = "jpeg" if extension in {"jpg", "jpeg"} else ("zip" if extension == "xlsx" else extension)
    if expected not in {kind, "csv"} and not (extension == "csv" and kind == "text"):
        raise HTTPException(status_code=400, detail="File extension and file signature do not match")
    password_protected = False
    if extension == "pdf":
        try:
            document = fitz.open(stream=data, filetype="pdf")
            password_protected = bool(document.needs_pass)
            document.close()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Malformed or unreadable PDF") from exc
        if password_protected:
            raise HTTPException(status_code=422, detail="Password-protected PDFs must be unlocked before upload")
    if extension == "xlsx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" not in names:
                    raise HTTPException(status_code=400, detail="Invalid XLSX container")
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=400, detail="Invalid XLSX container") from exc
    malware = _scan_malware(data, filename)
    return InspectionResult(hashlib.sha256(data).hexdigest(), len(data), extension, kind, password_protected, malware)

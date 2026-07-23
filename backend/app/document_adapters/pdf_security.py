"""Password-protected PDF handling.

Indian tax documents (Form 16, AIS, TIS, 26AS, bank statements) are almost
always password-protected. The workflow is: detect the lock on upload, ask the
CA for the password once, decrypt the file and store the *unlocked* bytes so
every later read (extraction, reconciliation, computation) needs no password,
and remember the working password (encrypted) for the case so sibling documents
unlock automatically.
"""

from __future__ import annotations

import fitz


def is_pdf(filename: str, mime_type: str, content: bytes) -> bool:
    if "pdf" in (mime_type or "").lower() or (filename or "").lower().endswith(".pdf"):
        return True
    return content[:5] == b"%PDF-"


def is_encrypted(content: bytes) -> bool:
    """True if the PDF requires a password to open."""
    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception:
        return False
    try:
        return bool(doc.needs_pass)
    finally:
        doc.close()


def unlock_pdf(content: bytes, password: str) -> bytes | None:
    """Return decrypted PDF bytes if ``password`` opens the file, else ``None``.

    An already-unlocked PDF is returned unchanged, so callers can pass any PDF.
    The returned bytes are re-saved without encryption, so downstream reads never
    need the password again.
    """
    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception:
        return None
    try:
        if not doc.needs_pass:
            return content
        if not doc.authenticate(password or ""):
            return None
        return doc.tobytes(encryption=fitz.PDF_ENCRYPT_NONE)
    except Exception:
        return None
    finally:
        doc.close()

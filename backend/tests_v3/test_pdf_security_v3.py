"""Tests for password-protected PDF detection and unlocking."""

from __future__ import annotations

import fitz

from app.document_adapters.pdf_security import is_encrypted, is_pdf, unlock_pdf


def _plain_pdf(text="Gross Salary 1250000"):
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _encrypted_pdf(user_pw="pan1234", text="Gross Salary 1250000"):
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), text)
    data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw=user_pw)
    doc.close()
    return data


def _readable_without_password(data):
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return not doc.needs_pass and doc[0].get_text().strip()
    finally:
        doc.close()


def test_is_encrypted_detects_locked_pdf():
    assert is_encrypted(_encrypted_pdf()) is True
    assert is_encrypted(_plain_pdf()) is False
    assert is_encrypted(b"not a pdf") is False


def test_unlock_with_correct_password_returns_decrypted_bytes():
    enc = _encrypted_pdf(user_pw="pan1234")
    out = unlock_pdf(enc, "pan1234")
    assert out is not None
    # the returned bytes open with no password and are readable
    assert _readable_without_password(out) == "Gross Salary 1250000"


def test_unlock_with_wrong_password_returns_none():
    assert unlock_pdf(_encrypted_pdf(user_pw="right"), "wrong") is None


def test_unlock_of_plain_pdf_is_passthrough():
    plain = _plain_pdf()
    assert unlock_pdf(plain, "anything") == plain


def test_is_pdf_detects_by_name_mime_and_magic():
    assert is_pdf("form16.pdf", "application/octet-stream", b"") is True
    assert is_pdf("x", "application/pdf", b"") is True
    assert is_pdf("x", "application/octet-stream", b"%PDF-1.7 ...") is True
    assert is_pdf("x.txt", "text/plain", b"hello") is False

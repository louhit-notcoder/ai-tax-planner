"""Column-level encryption for DPDP-sensitive fields.

Production refuses to start without explicit encryption and blind-index secrets.
Development may use explicit DEV_* secrets; no random ephemeral key is generated.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import warnings

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecureDataVault:
    def __init__(self):
        environment = os.environ.get("GREEN_PAPAYA_ENV", "development").lower()
        master = os.environ.get("KMS_DECRYPTION_SECRET_HEX")
        blind_secret = os.environ.get("BLIND_INDEX_SECRET")

        if not master and environment != "production":
            dev_secret = os.environ.get("DEV_ENCRYPTION_SECRET", "green-papaya-local-development-only")
            master = hashlib.sha256(dev_secret.encode()).hexdigest()
            warnings.warn("Using development encryption key; never use this configuration in production.", RuntimeWarning)
        if not blind_secret and environment != "production":
            blind_secret = os.environ.get("DEV_BLIND_INDEX_SECRET", "green-papaya-local-blind-index-only")

        if not master:
            raise RuntimeError("KMS_DECRYPTION_SECRET_HEX is required in production")
        if not blind_secret:
            raise RuntimeError("BLIND_INDEX_SECRET is required in production")
        if len(master) != 64:
            raise RuntimeError("KMS_DECRYPTION_SECRET_HEX must contain exactly 32 bytes encoded as 64 hex characters")

        self.key_bytes = bytes.fromhex(master)
        self.blind_index_key = blind_secret.encode()
        self.key_id = os.environ.get("KMS_KEY_ID", "development-key-v1")

    def encrypt(self, plaintext: str, associated_data: str = "green-papaya") -> str | None:
        if plaintext is None:
            return None
        aesgcm = AESGCM(self.key_bytes)
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, plaintext.encode(), associated_data.encode())
        return f"v1:{self.key_id}:{(nonce + ct).hex()}"

    def decrypt(self, payload: str, associated_data: str = "green-papaya") -> str | None:
        if not payload:
            return None
        if payload.startswith("v1:"):
            _, key_id, payload_hex = payload.split(":", 2)
            if key_id != self.key_id:
                raise RuntimeError(f"Encryption key {key_id} is not available")
        else:
            # Migration support for legacy records.
            payload_hex = payload
        raw = bytes.fromhex(payload_hex)
        aesgcm = AESGCM(self.key_bytes)
        nonce, ct = raw[:12], raw[12:]
        return aesgcm.decrypt(nonce, ct, associated_data.encode()).decode()

    def blind_hash(self, value: str) -> str:
        normalised = (value or "").strip().upper().encode()
        return hmac.new(self.blind_index_key, normalised, hashlib.sha256).hexdigest()


vault = SecureDataVault()

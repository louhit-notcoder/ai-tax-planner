"""Real decryptor for Income Tax Dept AIS Utility encrypted JSON exports.
Format: IV(32 hex) + salt(32 hex) + ciphertext(base64 or hex).
KDF: PBKDF2-HMAC-SHA256, 1000 iters, 32-byte key. Cipher: AES-CBC + PKCS7.
Password: pan.lower() + PASSWORD_MIDDLE + dob(ddmmyyyy), with fallbacks.
"""
import json
import base64
import logging
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

logger = logging.getLogger(__name__)
PASSWORD_MIDDLE = "GQ39%*g"


def _load_encrypted_payload(raw: str):
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"'):
        raw = json.loads(raw)
    if len(raw) < 64:
        raise ValueError("Encrypted AIS file too short (need IV+salt+ciphertext).")
    iv = bytes.fromhex(raw[:32])
    salt = bytes.fromhex(raw[32:64])
    ct_part = raw[64:]
    try:
        ciphertext = base64.b64decode(ct_part, validate=True)
    except Exception:
        ciphertext = bytes.fromhex(ct_part)
    if not ciphertext:
        raise ValueError("Ciphertext payload is empty.")
    return iv, salt, ciphertext


def _password_candidates(pan, dob, password_middle=None):
    lower, upper = pan.lower(), pan.upper()
    out, seen = [], set()

    def add(c):
        if c not in seen:
            seen.add(c)
            out.append(c)

    if password_middle is not None:
        add(f"{lower}{password_middle}{dob}")
        return out
    add(f"{lower}{PASSWORD_MIDDLE}{dob}")
    add(f"{lower}{dob}")
    add(f"{upper}{dob}")
    return out


def _decrypt(iv, salt, ciphertext, password):
    kdf = PBKDF2HMAC(algorithm=SHA256(), length=32, salt=salt, iterations=1000)
    key = kdf.derive(password.encode("utf-8"))
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    dec = cipher.decryptor()
    padded = dec.update(ciphertext) + dec.finalize()
    unpadder = PKCS7(algorithms.AES.block_size).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")


def decrypt_ais_text(raw_text: str, pan: str, dob: str, password: str = None) -> dict:
    iv, salt, ciphertext = _load_encrypted_payload(raw_text)
    candidates = [password] if password else _password_candidates(pan, dob)
    last_err = None
    for cand in candidates:
        try:
            plaintext = _decrypt(iv, salt, ciphertext, cand)
            return json.loads(plaintext)
        except Exception as e:
            last_err = e
    raise ValueError(f"Decryption failed. Check PAN/DOB/password. ({last_err})")


# ---- Extraction from decrypted (or plain) AIS/TIS JSON ----
SALARY_KW = ["salary"]
DIVIDEND_KW = ["dividend"]
INTEREST_KW = ["interest"]
TDS_KW = ["tax deducted", "tds"]
STCG_KW = ["short term", "short-term"]
LTCG_KW = ["long term", "long-term"]


def _to_float(v):
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return 0.0


def _walk_amounts(node, path=""):
    """Yield (context_label, amount) pairs from nested AIS JSON."""
    results = []
    if isinstance(node, dict):
        label_hint = ""
        for lk in ("infoDescription", "description", "informationDescription",
                   "categoryName", "infoCategory", "cat", "srcName", "name"):
            if isinstance(node.get(lk), str):
                label_hint = node[lk]
                break
        for ak in ("amount", "amountValue", "amtVal", "value", "totalAmount",
                   "amt", "processedAmount", "reportedValue", "amountCr"):
            if ak in node and isinstance(node[ak], (int, float, str)):
                amt = _to_float(node[ak])
                if amt:
                    results.append((f"{path} {label_hint}".strip().lower(), amt))
        for k, v in node.items():
            results.extend(_walk_amounts(v, f"{path} {label_hint} {k}".strip()))
    elif isinstance(node, list):
        for it in node:
            results.extend(_walk_amounts(it, path))
    return results


def extract_ais_prefill(ais_json: dict) -> dict:
    """Best-effort aggregation of AIS/TIS amounts by information category."""
    pairs = _walk_amounts(ais_json)
    agg = {"gross_salary": 0.0, "dividend": 0.0, "savings_interest": 0.0,
           "tds_deducted": 0.0, "stcg_equity": 0.0, "ltcg_equity": 0.0}
    for label, amt in pairs:
        l = label.lower()
        if any(k in l for k in TDS_KW):
            agg["tds_deducted"] += amt
        elif any(k in l for k in SALARY_KW):
            agg["gross_salary"] += amt
        elif any(k in l for k in STCG_KW):
            agg["stcg_equity"] += amt
        elif any(k in l for k in LTCG_KW):
            agg["ltcg_equity"] += amt
        elif any(k in l for k in DIVIDEND_KW):
            agg["dividend"] += amt
        elif any(k in l for k in INTEREST_KW):
            agg["savings_interest"] += amt
    agg = {k: round(v, 2) for k, v in agg.items()}
    agg["other_income"] = round(agg["dividend"] + agg["savings_interest"], 2)
    agg["_pairs_found"] = len(pairs)
    return agg

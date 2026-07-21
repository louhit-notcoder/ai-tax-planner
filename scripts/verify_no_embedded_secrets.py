#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", "node_modules", "__pycache__", ".pytest_cache", ".local_storage"}
PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "openai_style_key": re.compile(r"\bsk-(?:or-)?[A-Za-z0-9_-]{20,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "bearer_token": re.compile(r"Bearer\s+[A-Za-z0-9._-]{30,}"),
}
ALLOW_FILES = {".env.example"}

findings = []
for path in ROOT.rglob("*"):
    if not path.is_file() or any(part in SKIP for part in path.parts) or path.name in ALLOW_FILES:
        continue
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".pdf", ".zip", ".pyc", ".woff", ".woff2"}:
        continue
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        continue
    for name, pattern in PATTERNS.items():
        if pattern.search(text):
            findings.append(f"{name}: {path.relative_to(ROOT)}")
if findings:
    raise SystemExit("Potential embedded secrets found:\n" + "\n".join(findings))
print("No obvious embedded secrets found.")

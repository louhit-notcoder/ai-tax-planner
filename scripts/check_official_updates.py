#!/usr/bin/env python3
"""Detect changes in approved official sources without changing production rules.

The output is a review artefact. It never edits rule releases or activates code.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

SOURCES = [
    ("itr_downloads", "https://www.incometax.gov.in/iec/foportal/downloads/income-tax-returns"),
    ("itr1_validation", "https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-05/CBDT_e-Filing_ITR%201_Validation%20Rules_AY%202026-27.pdf"),
    ("itr2_validation", "https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-05/CBDT__e-Filing_ITR%202_Validation%20Rules_AY%202026-27_V1.0.pdf"),
]


def main():
    output = {"checked_at": datetime.now(timezone.utc).isoformat(), "sources": []}
    for source_id, url in SOURCES:
        response = requests.get(url, timeout=60, headers={"User-Agent": "GreenPapaya-LawMonitor/1.0"})
        response.raise_for_status()
        output["sources"].append({
            "source_id": source_id,
            "url": url,
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type"),
            "last_modified": response.headers.get("last-modified"),
            "etag": response.headers.get("etag"),
            "sha256": hashlib.sha256(response.content).hexdigest(),
            "bytes": len(response.content),
        })
    path = Path("official_update_report.json")
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(path.resolve())


if __name__ == "__main__":
    main()

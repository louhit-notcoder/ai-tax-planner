from __future__ import annotations

import re


OFFICIAL_SOURCES = [
    {
        "source_id": "ITD-AY2026-27-SALARIED",
        "title": "Salaried Individuals for AY 2026-27",
        "source_type": "portal_guidance",
        "act_namespace": "ITA_1961",
        "section_or_rule": None,
        "tax_period": "AY 2026-27",
        "official_url": "https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-1",
        "keywords": ["itr-1", "salary", "house property", "112a", "return form", "resident"],
        "summary": "Official return eligibility and tax-regime guidance for salaried individuals for AY 2026-27.",
    },
    {
        "source_id": "ITD-ITR1-VALIDATION-AY2026-27-V1",
        "title": "ITR-1 Validation Rules AY 2026-27 Version 1.0",
        "source_type": "itr_validation",
        "act_namespace": "ITA_1961",
        "section_or_rule": None,
        "tax_period": "AY 2026-27",
        "official_url": "https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-05/CBDT_e-Filing_ITR%201_Validation%20Rules_AY%202026-27.pdf",
        "keywords": ["itr-1", "validation", "schema", "error", "rebate", "tax payable"],
        "summary": "Official validation rules published by the Income Tax Department for ITR-1.",
    },
    {
        "source_id": "ITD-ITR2-VALIDATION-AY2026-27-V1",
        "title": "ITR-2 Validation Rules AY 2026-27 Version 1.0",
        "source_type": "itr_validation",
        "act_namespace": "ITA_1961",
        "section_or_rule": None,
        "tax_period": "AY 2026-27",
        "official_url": "https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-05/CBDT__e-Filing_ITR%202_Validation%20Rules_AY%202026-27_V1.0.pdf",
        "keywords": ["itr-2", "validation", "capital gains", "schedule", "rebate", "tax payable"],
        "summary": "Official validation rules published by the Income Tax Department for ITR-2.",
    },
    {
        "source_id": "ITD-ITR-DOWNLOADS-AY2026-27",
        "title": "Income-tax Return Utilities, Schemas and Validation Rules",
        "source_type": "itr_schema",
        "act_namespace": "ITA_1961",
        "section_or_rule": None,
        "tax_period": "AY 2026-27",
        "official_url": "https://www.incometax.gov.in/iec/foportal/downloads/income-tax-returns",
        "keywords": ["schema", "utility", "json", "offline", "download", "version"],
        "summary": "Official download page for form-specific schemas, utilities and validation rules.",
    },
]


PORTAL_GUIDES = {
    "download_ais": {
        "portal": "income_tax",
        "title": "Download AIS",
        "steps": [
            "Sign in to the Income Tax e-Filing portal using the taxpayer account.",
            "Open the Annual Information Statement service from the Services menu.",
            "Choose the relevant financial year.",
            "Download the available AIS/TIS file in the portal-supported format.",
            "Upload the original downloaded file to the active Green Papaya case.",
        ],
        "review_note": "Portal labels can change. Confirm the current screen before sending this guide to a client.",
    },
    "download_26as": {
        "portal": "income_tax",
        "title": "Download Form 26AS",
        "steps": [
            "Sign in to the Income Tax e-Filing portal.",
            "Open the tax-credit statement/Form 26AS service.",
            "Continue to the authorised statement provider when prompted.",
            "Select the relevant assessment year and preferred view or download format.",
            "Upload the downloaded statement to the active case.",
        ],
        "review_note": "Never ask a client to share their portal password or OTP.",
    },
}


def search_tax_law(query: str, tax_period: str = "AY 2026-27", act_namespace: str = "ITA_1961") -> list[dict]:
    tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    scored = []
    for source in OFFICIAL_SOURCES:
        if source["tax_period"] != tax_period or source["act_namespace"] != act_namespace:
            continue
        haystack = " ".join([source["title"], source["summary"], *source["keywords"]]).lower()
        score = sum(1 for token in tokens if token in haystack)
        if score:
            scored.append((score, source))
    scored.sort(key=lambda item: (-item[0], item[1]["title"]))
    return [item[1] for item in scored[:10]]

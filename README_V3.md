# Green Papaya AI Tax Assistant — V3 production code foundation

Green Papaya V3 is a PostgreSQL/FastAPI/React implementation of the approved
build-to-production blueprint. It is designed for CA-supervised preparation of
individual Indian income-tax returns with deterministic calculations, page-level
evidence, maker-checker approval and fail-closed ITR exports.

## Use this as a new project, not an in-place overwrite

Extract this repository beside the existing project. Keep a full backup and do
not copy files over the old tree. Follow `MIGRATION_FROM_EXISTING.md` to migrate
configuration and selected data. The V3 APIs, database and authentication model
are intentionally incompatible with the unsafe V1/V2 Mongo workflow.

## Local start

```bash
cp .env.example .env
# Replace every CHANGE_ME value in .env
docker compose up --build
```

Then:

1. Open `http://localhost:3000`.
2. Bootstrap the first firm owner in development, or run
   `python scripts/provision_firm_owner.py`.
3. Enrol MFA.
4. Create a client and AY 2026–27 case.
5. Upload documents, review candidate facts, compute, review and approve.

See `docs/LOCAL_SETUP.md` for non-Docker setup.

## Active architecture

- PostgreSQL is the canonical financial/audit system of record.
- Redis handles distributed rate limits, job coordination and ephemeral locks.
- S3-compatible encrypted object storage holds immutable documents/evidence.
- ClamAV scans uploaded files before persistence.
- FastAPI exposes tenant- and case-authorised services.
- The deterministic engine accepts an immutable fact snapshot and pinned rules.
- The AI has a strict allowlisted tool gateway and no database credentials.
- ITR-1/ITR-2 export remains fail closed until official schemas are pinned and an
  approved official-utility validation adapter passes.

## Validation performed in this delivery

- 31 automated backend/API/engine/security/document/export/legal tests.
- Deterministic AY 2026–27 boundary and reproducibility tests.
- Explicit Form 16, AIS deduplication, broker transaction and legal retrieval tests.
- Schema-draft-aware export validation and deterministic export snapshot tests.
- Python compile/import validation.
- Static parsing of all active and retained frontend JS/JSX/TS/TSX files.
- Secret-pattern scan.

The frontend includes a reproducible `package-lock.json`. An offline `npm ci` completed with zero audit vulnerabilities, and the TypeScript/Vite production bundle built successfully in this environment.

## Mandatory non-code release gates

No code generator can truthfully complete these approvals:

- independent CA validation of the golden-case library;
- parallel comparison with the current official utility and trusted CA software;
- independent authenticated penetration test;
- Indian privacy/legal review and executed customer/DPA documents;
- production cloud/domain/provider choices and vendor agreements;
- controlled pilot with real CA reviewer sign-off.

See `docs/EXTERNAL_RELEASE_GATES.md` and `docs/INPUTS_REQUIRED.md`.

# Green Papaya V3 build report

This delivery converts the reviewed prototype/V2 foundation into one coherent PostgreSQL production code path. It implements the code-side controls in the approved blueprint while keeping independent tax, legal and security certification as external release gates.

## Automated checks completed in this build environment

- **31/31 backend tests passed** across engine, API, tenant isolation, maker-checker approval, locked-case mutation, document adapters, legal retrieval and fail-closed export.
- Python compilation passed for the active backend and operational scripts.
- FastAPI imported successfully with **57 registered routes / 48 OpenAPI paths**.
- A fresh Alembic migration completed successfully and created **33 tables**.
- All **65 frontend JS/JSX/TS/TSX files** passed static syntax parsing.
- `npm ci --offline` completed, npm reported **0 vulnerabilities**, and the TypeScript/Vite production bundle built successfully (**1,776 modules transformed**).
- Docker Compose YAML parsed with PostgreSQL, Redis, MinIO, ClamAV, backend, worker and frontend services.
- Embedded-secret pattern scan passed.
- The model-evaluation harness passed against deterministic mock responses; this does not approve any real model for production.

## Additional hardening completed

- Export accepts only `COMPLETE` computations.
- Export creation/verification dates are explicit inputs and included in immutable payload hashes.
- JSON Schema validation selects the draft declared by the pinned official schema.
- Test configuration is initialised before module collection, avoiding environment-order-dependent security behaviour.
- Added Form 16 evidence extraction, AIS transaction deduplication and broker transaction-level parser tests.
- Added approved-source-only legal retrieval tests.
- Added a synthetic pinned-schema test for deterministic ITR payload generation.
- Added a privacy-safe assistant model evaluation suite and runner.

## Checks that could not be completed here

- Docker is unavailable in this runtime, so `docker compose up` and image execution were not run.
- Terraform is unavailable in this runtime, so `terraform validate` was not run.
- The official ITR schema JSON files could be verified online but could not be downloaded into the code container. The sync script downloads, hashes and pins them in the target environment.
- The Income Tax Department utility does not provide a guaranteed server-side CLI contract. Final utility compatibility therefore requires the configured adapter or a controlled human utility-validation workflow.

## Mandatory external evidence

A repository cannot independently perform a third-party penetration test, issue an Indian legal/privacy opinion, certify real tax cases, execute cloud/vendor contracts or complete a controlled CA pilot. Those gates are described in `EXTERNAL_RELEASE_GATES.md`.

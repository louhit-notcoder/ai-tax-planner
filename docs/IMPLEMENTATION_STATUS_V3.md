# V3 implementation status

## Code-complete production foundation

- PostgreSQL data model and Alembic migration.
- tenant, membership, invitation, SMTP delivery, role and object-level case authorization.
- MFA enrolment and verification; refresh sessions preserve MFA state; production auth tokens remain HttpOnly and are not returned in response bodies.
- encrypted PAN/DOB/phone fields and keyed blind indexes.
- immutable object-storage abstraction, upload signatures, PDF password rejection,
  duplicate detection and ClamAV integration.
- versioned documents, extraction runs, evidence claims, candidate facts,
  canonical facts, immutable snapshots and append-only audit events.
- explicit adapters for Form 16, AIS JSON, TIS/26AS, major banks, broker CSV and
  previous-year ITR JSON.
- property-level, employment-level and transaction-level deterministic inputs.
- AY 2026–27 deterministic engine with Decimal arithmetic, calculation trace,
  regime comparison, supported deductions, tax credits and fail-closed review
  paths for complex/business/foreign cases.
- return-form eligibility service.
- persisted missing-item and reconciliation workflows.
- maker-checker computation approval and case locking.
- allowlisted AI gateway with server-bound case context and persisted drafts.
- official legal-source ingestion and approved-source retrieval.
- schema-driven ITR-1/ITR-2 exporter, pinned schema hashes, schema-draft-aware validation, explicit export dates, utility-validation adapter and immutable export snapshots.
- privacy requests, consent/security/model-evaluation entities and an executable synthetic model-evaluation harness.
- React/Vite CA dashboard, MFA, case workspace, evidence/candidate/reconciliation/
  computation/export/audit panels.
- Docker Compose, CI security scans, Terraform production data foundation, load
  profile, retention/migration/provisioning scripts and operational documentation.

## Deliberately fail-closed or expert-review only

The code models and organises NRI/RNOR, foreign assets/income, FTC/Form 67,
business, F&O, VDA, unlisted securities and complex losses. They are not marketed
as fully automated until CA-certified golden suites are supplied. Any unsupported
or insufficiently evidenced scenario is BLOCKED, UNSUPPORTED or PROVISIONAL.

## External work still required

See `EXTERNAL_RELEASE_GATES.md`. A repository cannot perform an independent
penetration test, issue a legal opinion or certify tax correctness on real cases.

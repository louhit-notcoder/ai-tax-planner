# Security threat model

## Protected assets

Taxpayer identity, PAN, bank and brokerage data, evidence files, canonical facts,
computation/export snapshots, legal/rule releases, credentials and audit history.

## Trust boundaries

Browser → WAF/CDN → API; API → PostgreSQL/Redis/S3; workers → documents/model
providers; administrators → cloud/KMS; AI model → allowlisted tool gateway only.

## Primary threats and controls

- **Cross-tenant access:** tenant predicates, case assignments, opaque IDs, tests.
- **Privilege escalation:** invitation-only roles, MFA, active membership check.
- **Prompt injection:** document text is untrusted; no generic fetch/SQL/DB tools;
  strict literal tool schemas and server-bound case IDs.
- **Document attacks:** signatures, size caps, password rejection, ClamAV, isolated
  parsing workers and no active-content execution.
- **Fact/computation tampering:** candidate review, canonical versions, snapshot and
  result hashes, maker-checker approvals, immutable locked cases.
- **Export bypass:** pinned schema hash, schema validator, utility adapter and
  reviewer approval all required.
- **Secret/PII leakage:** KMS/secrets manager, encrypted fields, log redaction,
  provider ZDR/data-collection controls.
- **Availability/abuse:** Redis rate limits, queues, autoscaling, backups and WAF.

Independent penetration testing is mandatory before production.

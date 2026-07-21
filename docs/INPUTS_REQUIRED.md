# Inputs required from the product owner before live production

The code is prepared to accept these inputs; placeholders are intentionally not
invented.

## Required for local/staging setup

- firm name, owner name and owner email;
- strong application secrets and encryption keys;
- PostgreSQL, Redis and S3/MinIO connection details;
- frontend and API URLs/CORS origins;
- preferred AI provider/model and its enterprise privacy/ZDR settings;
- approved SMTP invitation-delivery provider, sender address and production app URL;
- client-communication provider only when draft sending is enabled.

## Required for official export activation

- approved copies/hashes of current AY 2026–27 ITR-1 and ITR-2 schemas;
- approved published validation-rule versions;
- a documented command or controlled human workflow that runs the current
  official utility validation;
- software/intermediary identifiers required for the intended filing workflow;
- CA reviewer approval policy.

## Required for tax certification

- at least 100 anonymised historical cases initially, expanding to the targets in
  `docs/CA_GOLDEN_CASE_GUIDE.md`;
- expected outputs from the official utility and the firm’s trusted software;
- a named CA tax-domain owner;
- signed decisions for ambiguous tax positions and supported/unsupported scope.

## Required for cloud production

- cloud account and Indian region choice;
- domain and ACM/TLS certificate;
- signed container image digests;
- backup retention/RPO/RTO approval;
- on-call and incident contacts;
- data-retention periods;
- approved subprocessors and model provider contracts.

## Required external sign-offs

- independent penetration-test report;
- privacy and customer-contract legal opinions;
- CA golden-case certification;
- pilot acceptance report.

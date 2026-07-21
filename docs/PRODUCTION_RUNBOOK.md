# Production runbook

## Deployment

1. Provision `infra/terraform` using a remote encrypted Terraform state backend.
2. Push signed/scanned backend and frontend images to the provisioned ECR repos.
3. Store application secrets in Secrets Manager/KMS—never Terraform plaintext.
4. Configure private ECS tasks, ALB/ACM/domain, WAF association and autoscaling.
5. Run Alembic as a one-off migration task before the new application rollout.
6. Run backend smoke tests, schema-hash verification and synthetic tenant checks.
7. Deploy canary, monitor, then expand.

## Required alarms

5xx/error rate, permission-denial anomaly, queue age, parser failures, schema/
utility failures, DB connections/replica health, Redis failures, S3 access denied,
backup failures, KMS errors, AI latency/cost and suspicious authentication events.

## Backup/restore

Use RDS point-in-time recovery, multi-AZ, S3 versioning and cross-account backup
vaults. Test restore quarterly and before filing season. Record achieved RPO/RTO.

## Incident response

- stop/feature-flag risky modules;
- revoke sessions/provider keys;
- preserve audit/security logs;
- isolate affected tenant when appropriate;
- involve legal/privacy/security owners;
- follow applicable CERT-In and contractual notification obligations;
- perform post-incident review and regression test.

## Rule/schema update

Detect/download → hash → tax review → code/test changes → staging/differential
suite → approval → feature-flagged activation. Never activate automatically.

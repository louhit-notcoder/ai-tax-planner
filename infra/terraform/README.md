# AWS production foundation

Creates the encrypted production data foundation in `ap-south-1`: multi-AZ VPC,
PostgreSQL 16, TLS/encrypted Redis, versioned private S3, KMS, ECR, ECS cluster,
CloudWatch log groups, Secrets Manager and regional WAF. Final ECS services/ALB/DNS
need the owner's domain, ACM certificate and signed image digests; follow
`docs/PRODUCTION_RUNBOOK.md`.

Never commit `terraform.tfvars` or state. Use a remote encrypted Terraform backend.

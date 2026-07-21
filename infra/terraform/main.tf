locals {
  name = "${var.project}-${var.environment}"
  tags = {
    Project = var.project
    Environment = var.environment
    ManagedBy = "Terraform"
    DataClassification = "SensitiveFinancialData"
  }
}

data "aws_availability_zones" "available" { state = "available" }

data "aws_caller_identity" "current" {}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.19.0"
  name = local.name
  cidr = "10.60.0.0/16"
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
  public_subnets = ["10.60.0.0/24", "10.60.1.0/24"]
  private_subnets = ["10.60.10.0/24", "10.60.11.0/24"]
  database_subnets = ["10.60.20.0/24", "10.60.21.0/24"]
  enable_nat_gateway = true
  single_nat_gateway = false
  one_nat_gateway_per_az = true
  enable_dns_hostnames = true
  enable_dns_support = true
  create_database_subnet_group = true
  tags = local.tags
}

resource "aws_kms_key" "application" {
  description = "Green Papaya application, database, object and log encryption"
  enable_key_rotation = true
  deletion_window_in_days = 30
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid = "EnableRootPermissions"
      Effect = "Allow"
      Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
      Action = "kms:*"
      Resource = "*"
    }]
  })
}
resource "aws_kms_alias" "application" { name = "alias/${local.name}"; target_key_id = aws_kms_key.application.key_id }

resource "aws_s3_bucket" "documents" { bucket = "${local.name}-documents-${data.aws_caller_identity.current.account_id}" }
resource "aws_s3_bucket_public_access_block" "documents" {
  bucket = aws_s3_bucket.documents.id
  block_public_acls = true
  block_public_policy = true
  ignore_public_acls = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule { apply_server_side_encryption_by_default { kms_master_key_id = aws_kms_key.application.arn; sse_algorithm = "aws:kms" }; bucket_key_enabled = true }
}
resource "aws_s3_bucket_lifecycle_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    id = "abort-incomplete"
    status = "Enabled"
    abort_incomplete_multipart_upload { days_after_initiation = 7 }
    noncurrent_version_expiration { noncurrent_days = 365 }
  }
}

resource "aws_security_group" "database" {
  name = "${local.name}-database"
  vpc_id = module.vpc.vpc_id
  egress { from_port = 0; to_port = 0; protocol = "-1"; cidr_blocks = ["0.0.0.0/0"] }
}
resource "aws_security_group" "application" {
  name = "${local.name}-application"
  vpc_id = module.vpc.vpc_id
  egress { from_port = 0; to_port = 0; protocol = "-1"; cidr_blocks = ["0.0.0.0/0"] }
}
resource "aws_vpc_security_group_ingress_rule" "postgres_from_app" {
  security_group_id = aws_security_group.database.id
  referenced_security_group_id = aws_security_group.application.id
  from_port = 5432; to_port = 5432; ip_protocol = "tcp"
}
resource "aws_vpc_security_group_ingress_rule" "redis_from_app" {
  security_group_id = aws_security_group.database.id
  referenced_security_group_id = aws_security_group.application.id
  from_port = 6379; to_port = 6379; ip_protocol = "tcp"
}

resource "aws_db_instance" "postgres" {
  identifier = "${local.name}-postgres"
  engine = "postgres"
  engine_version = "16.4"
  instance_class = var.db_instance_class
  allocated_storage = 100
  max_allocated_storage = 1000
  storage_type = "gp3"
  storage_encrypted = true
  kms_key_id = aws_kms_key.application.arn
  db_name = var.db_name
  username = var.db_username
  password = var.db_password
  port = 5432
  db_subnet_group_name = module.vpc.database_subnet_group_name
  vpc_security_group_ids = [aws_security_group.database.id]
  backup_retention_period = var.backup_retention_days
  backup_window = "19:00-20:00"
  maintenance_window = "sun:20:30-sun:21:30"
  deletion_protection = true
  skip_final_snapshot = false
  final_snapshot_identifier = "${local.name}-final"
  multi_az = true
  auto_minor_version_upgrade = true
  performance_insights_enabled = true
  performance_insights_kms_key_id = aws_kms_key.application.arn
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
}

resource "aws_elasticache_subnet_group" "redis" { name = local.name; subnet_ids = module.vpc.private_subnets }
resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${local.name}-redis"
  description = "Green Papaya queues, locks and rate limits"
  node_type = var.redis_node_type
  port = 6379
  parameter_group_name = "default.redis7"
  subnet_group_name = aws_elasticache_subnet_group.redis.name
  security_group_ids = [aws_security_group.database.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token = random_password.redis.result
  automatic_failover_enabled = true
  multi_az_enabled = true
  num_cache_clusters = 2
  snapshot_retention_limit = 7
}
resource "random_password" "redis" { length = 48; special = false }

resource "aws_ecr_repository" "backend" { name = "${local.name}-backend"; image_scanning_configuration { scan_on_push = true }; encryption_configuration { encryption_type = "KMS"; kms_key = aws_kms_key.application.arn } }
resource "aws_ecr_repository" "frontend" { name = "${local.name}-frontend"; image_scanning_configuration { scan_on_push = true }; encryption_configuration { encryption_type = "KMS"; kms_key = aws_kms_key.application.arn } }
resource "aws_ecs_cluster" "main" { name = local.name; setting { name = "containerInsights"; value = "enabled" } }
resource "aws_cloudwatch_log_group" "backend" { name = "/ecs/${local.name}/backend"; retention_in_days = 365; kms_key_id = aws_kms_key.application.arn }
resource "aws_cloudwatch_log_group" "frontend" { name = "/ecs/${local.name}/frontend"; retention_in_days = 365; kms_key_id = aws_kms_key.application.arn }

resource "aws_secretsmanager_secret" "application" { name = "${local.name}/application"; kms_key_id = aws_kms_key.application.arn }

resource "aws_wafv2_web_acl" "main" {
  name = local.name
  scope = "REGIONAL"
  default_action { allow {} }
  visibility_config { cloudwatch_metrics_enabled = true; metric_name = local.name; sampled_requests_enabled = true }
  rule {
    name = "AWSManagedCommon"
    priority = 10
    override_action { none {} }
    statement { managed_rule_group_statement { name = "AWSManagedRulesCommonRuleSet"; vendor_name = "AWS" } }
    visibility_config { cloudwatch_metrics_enabled = true; metric_name = "common"; sampled_requests_enabled = true }
  }
  rule {
    name = "AWSManagedKnownBadInputs"
    priority = 20
    override_action { none {} }
    statement { managed_rule_group_statement { name = "AWSManagedRulesKnownBadInputsRuleSet"; vendor_name = "AWS" } }
    visibility_config { cloudwatch_metrics_enabled = true; metric_name = "bad-inputs"; sampled_requests_enabled = true }
  }
}

# ECS task definitions/services, ALB listener certificates and DNS are intentionally
# parameterised in the deployment runbook because they require the final domain,
# ACM certificate and image digests. The cluster, private networking, encrypted data
# services, registries, secrets, logs and WAF are provisioned here.

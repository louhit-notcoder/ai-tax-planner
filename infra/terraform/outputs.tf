output "vpc_id" { value = module.vpc.vpc_id }
output "private_subnet_ids" { value = module.vpc.private_subnets }
output "application_security_group_id" { value = aws_security_group.application.id }
output "postgres_endpoint" { value = aws_db_instance.postgres.address; sensitive = true }
output "redis_endpoint" { value = aws_elasticache_replication_group.redis.primary_endpoint_address; sensitive = true }
output "documents_bucket" { value = aws_s3_bucket.documents.id }
output "kms_key_arn" { value = aws_kms_key.application.arn }
output "backend_repository_url" { value = aws_ecr_repository.backend.repository_url }
output "frontend_repository_url" { value = aws_ecr_repository.frontend.repository_url }
output "ecs_cluster_arn" { value = aws_ecs_cluster.main.arn }
output "application_secret_arn" { value = aws_secretsmanager_secret.application.arn }
output "waf_acl_arn" { value = aws_wafv2_web_acl.main.arn }

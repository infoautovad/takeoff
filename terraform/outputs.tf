output "vpc_id" {
  value = aws_vpc.main.id
}

output "alb_dns_name" {
  value = aws_lb.app.dns_name
}

output "cloudfront_domain_name" {
  value       = aws_cloudfront_distribution.main.domain_name
  description = "Primary user-facing URL (https://<this>)"
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.main.id
}

output "frontend_bucket" {
  value = aws_s3_bucket.frontend.id
}

output "uploads_bucket" {
  value = aws_s3_bucket.uploads.id
}

output "rds_endpoint" {
  value = aws_db_instance.main.address
}

output "app_instance_id" {
  value = aws_instance.app.id
}

output "db_secret_arn" {
  value = aws_secretsmanager_secret.db.arn
}

output "app_secret_arn" {
  value = aws_secretsmanager_secret.app.arn
}

output "waf_web_acl_arn" {
  value = var.enable_waf ? aws_wafv2_web_acl.cdn[0].arn : null
}

output "cloudwatch_dashboard" {
  value = aws_cloudwatch_dashboard.main.dashboard_name
}

output "ses_from_email" {
  value = var.ses_from_email
}

output "next_steps" {
  value = <<-EOT
    1) Deploy Vue build to s3://${aws_s3_bucket.frontend.id} then invalidate CloudFront ${aws_cloudfront_distribution.main.id}
    2) Deploy FastAPI to EC2 ${aws_instance.app.id} (SSM Session Manager)
    3) Load DB URL from Secrets Manager ${aws_secretsmanager_secret.db.name}
    4) Open app at https://${aws_cloudfront_distribution.main.domain_name}
  EOT
}

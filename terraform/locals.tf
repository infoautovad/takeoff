locals {
  name_prefix = "${var.project_name}-${var.environment}"

  azs = slice(var.availability_zones, 0, 2)

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
  }

  frontend_bucket_name = "${local.name_prefix}-frontend-${data.aws_caller_identity.current.account_id}"
  uploads_bucket_name  = "${local.name_prefix}-uploads-${data.aws_caller_identity.current.account_id}"
  logs_bucket_name     = "${local.name_prefix}-logs-${data.aws_caller_identity.current.account_id}"

  alb_https_enabled = var.create_acm_certificate && var.domain_name != "" && var.route53_zone_id != ""
  cdn_custom_domain = local.alb_https_enabled
}

data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

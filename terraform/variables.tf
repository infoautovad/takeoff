variable "project_name" {
  description = "Short project name used for resource naming"
  type        = string
  default     = "civilmind"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "aws_region" {
  description = "Primary AWS region for app resources (EC2, RDS, S3 origin region)"
  type        = string
  default     = "us-east-1"
}

variable "domain_name" {
  description = "Root domain for the app (example: civilmind.example.com). Leave empty to use CloudFront default domain."
  type        = string
  default     = ""
}

variable "create_acm_certificate" {
  description = "Create ACM cert in us-east-1 for CloudFront custom domain"
  type        = bool
  default     = false
}

variable "route53_zone_id" {
  description = "Public Route53 hosted zone ID for DNS validation and records. Required when create_acm_certificate=true."
  type        = string
  default     = ""
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.40.0.0/24", "10.40.1.0/24"]
}

variable "private_app_subnet_cidrs" {
  type    = list(string)
  default = ["10.40.10.0/24", "10.40.11.0/24"]
}

variable "private_db_subnet_cidrs" {
  type    = list(string)
  default = ["10.40.20.0/24", "10.40.21.0/24"]
}

variable "availability_zones" {
  description = "AZs to use (must match region)"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "admin_cidr_blocks" {
  description = "CIDRs allowed for SSH to bastion/EC2 (never use 0.0.0.0/0 in production)"
  type        = list(string)
  default     = []
}

variable "enable_bastion" {
  description = "Create a bastion host in a public subnet for admin SSH"
  type        = bool
  default     = false
}

variable "bastion_key_name" {
  description = "Existing EC2 key pair name for bastion/app SSH"
  type        = string
  default     = ""
}

variable "app_instance_type" {
  type    = string
  default = "t3.medium"
}

variable "app_ami_id" {
  description = "Optional AMI override. Empty = latest Amazon Linux 2023"
  type        = string
  default     = ""
}

variable "db_instance_class" {
  type    = string
  default = "db.t3.medium"
}

variable "db_name" {
  type    = string
  default = "civilmind"
}

variable "db_username" {
  type    = string
  default = "civilmind_admin"
}

variable "db_allocated_storage" {
  type    = number
  default = 50
}

variable "db_multi_az" {
  type    = bool
  default = true
}

variable "db_deletion_protection" {
  type    = bool
  default = true
}

variable "db_backup_retention_days" {
  type    = number
  default = 7
}

variable "ses_from_email" {
  description = "Verified SES sender email (must be verified in SES)"
  type        = string
  default     = ""
}

variable "alarm_email" {
  description = "Email for CloudWatch alarm SNS notifications"
  type        = string
  default     = ""
}

variable "enable_waf" {
  type    = bool
  default = true
}

variable "enable_vpc_flow_logs" {
  type    = bool
  default = true
}

variable "allowed_cors_origins" {
  description = "Extra CORS origins for app (CloudFront domain is added automatically)"
  type        = list(string)
  default     = []
}

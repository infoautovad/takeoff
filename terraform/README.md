# AutoVAD — AWS Terraform

Secure infrastructure matching your stack:

| Service | Purpose |
| --- | --- |
| VPC + public/private subnets | Network isolation |
| ALB + private EC2 | FastAPI backend |
| RDS PostgreSQL (private, SSL forced) | Database |
| S3 (frontend + uploads + logs) | Storage |
| CloudFront | CDN for Vue app + `/api/*` to ALB |
| WAFv2 | Edge protection (OWASP, SQLi, bad inputs, rate limit) |
| IAM roles + instance profile | No long-lived access keys on EC2 |
| Secrets Manager + KMS | DB/app secrets encrypted |
| CloudWatch | Logs, alarms, dashboard |
| SES | Transactional email |
| Security Groups | Least-privilege traffic |
| VPC Flow Logs | Network audit trail |
| IMDSv2 + encrypted EBS | EC2 hardening |

## Architecture

```text
Users
  │
  ▼
CloudFront + WAF
  ├── static /*     → S3 frontend (OAC, private)
  └── /api/*,/health → ALB → private EC2 (FastAPI)
                              │
                              ├── RDS Postgres (private subnets, SSL)
                              ├── S3 uploads (KMS)
                              ├── Secrets Manager
                              ├── CloudWatch
                              └── SES
```

## Prerequisites

1. AWS account + credentials (`aws configure` or env vars)
2. Terraform `>= 1.6`
3. Optional: Route53 hosted zone for custom domain
4. Optional: EC2 key pair if using bastion

## Apply

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars

terraform init
terraform plan
terraform apply
```

## Important security defaults

- RDS is **not** publicly accessible
- App EC2 is in **private** subnets (no public IP)
- S3 buckets block all public access
- CloudFront HTTPS redirect + TLS 1.2+
- WAF managed rules + IP rate limit
- Secrets stored in Secrets Manager (KMS)
- SSH closed unless you set `admin_cidr_blocks`
- Prefer **SSM Session Manager** over SSH (`AmazonSSMManagedInstanceCore` attached)

## Custom domain (optional)

In `terraform.tfvars`:

```hcl
domain_name            = "autovad.example.com"
create_acm_certificate = true
route53_zone_id        = "ZXXXXXXXX"
```

This creates ACM certs, DNS validation, `A` aliases for apex/www → CloudFront and `api.` → ALB.

## After apply

1. Build frontend and sync to the frontend bucket output  
2. Invalidate CloudFront  
3. Deploy backend to the EC2 instance via SSM  
4. Set `OPENAI_API_KEY` later in the app secret in Secrets Manager  
5. Confirm SES identity / leave sandbox if needed  

## Cost note

NAT Gateway, Multi-AZ RDS, WAF, and CloudFront incur ongoing charges. For cheaper non-prod, set:

```hcl
environment            = "dev"
db_multi_az            = false
db_deletion_protection = false
db_instance_class      = "db.t3.micro"
app_instance_type      = "t3.small"
```

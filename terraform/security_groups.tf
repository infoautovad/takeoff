resource "aws_security_group" "alb" {
  name        = "${local.name_prefix}-alb-sg"
  description = "ALB security group - HTTPS/HTTP from internet"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "${local.name_prefix}-alb-sg"
  }
}

resource "aws_security_group" "app" {
  name        = "${local.name_prefix}-app-sg"
  description = "App EC2 - only from ALB"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "${local.name_prefix}-app-sg"
  }
}

resource "aws_security_group" "rds" {
  name        = "${local.name_prefix}-rds-sg"
  description = "RDS PostgreSQL - only from app EC2"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "${local.name_prefix}-rds-sg"
  }
}

resource "aws_security_group" "bastion" {
  count       = var.enable_bastion ? 1 : 0
  name        = "${local.name_prefix}-bastion-sg"
  description = "Bastion SSH from admin CIDRs only"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "${local.name_prefix}-bastion-sg"
  }
}

# ---- ALB rules ----
resource "aws_security_group_rule" "alb_ingress_https" {
  type              = "ingress"
  security_group_id = aws_security_group.alb.id
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  description       = "HTTPS from internet"
}

resource "aws_security_group_rule" "alb_ingress_http" {
  type              = "ingress"
  security_group_id = aws_security_group.alb.id
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  description       = "HTTP redirect from internet"
}

resource "aws_security_group_rule" "alb_egress_app" {
  type                     = "egress"
  security_group_id        = aws_security_group.alb.id
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.app.id
  description              = "Forward to app EC2"
}

# ---- App rules ----
resource "aws_security_group_rule" "app_ingress_alb" {
  type                     = "ingress"
  security_group_id        = aws_security_group.app.id
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.alb.id
  description              = "FastAPI from ALB"
}

resource "aws_security_group_rule" "app_ingress_ssh_admin" {
  count             = length(var.admin_cidr_blocks) > 0 ? 1 : 0
  type              = "ingress"
  security_group_id = aws_security_group.app.id
  from_port         = 22
  to_port           = 22
  protocol          = "tcp"
  cidr_blocks       = var.admin_cidr_blocks
  description       = "SSH from admin CIDRs"
}

resource "aws_security_group_rule" "app_ingress_ssh_bastion" {
  count                    = var.enable_bastion ? 1 : 0
  type                     = "ingress"
  security_group_id        = aws_security_group.app.id
  from_port                = 22
  to_port                  = 22
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.bastion[0].id
  description              = "SSH from bastion"
}

resource "aws_security_group_rule" "app_egress_https" {
  type              = "egress"
  security_group_id = aws_security_group.app.id
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  description       = "HTTPS outbound"
}

resource "aws_security_group_rule" "app_egress_http" {
  type              = "egress"
  security_group_id = aws_security_group.app.id
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  description       = "HTTP outbound for package mirrors"
}

resource "aws_security_group_rule" "app_egress_rds" {
  type                     = "egress"
  security_group_id        = aws_security_group.app.id
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.rds.id
  description              = "PostgreSQL to RDS"
}

# ---- RDS rules ----
resource "aws_security_group_rule" "rds_ingress_app" {
  type                     = "ingress"
  security_group_id        = aws_security_group.rds.id
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.app.id
  description              = "Postgres from app"
}

# ---- Bastion rules ----
resource "aws_security_group_rule" "bastion_ingress_ssh" {
  count             = var.enable_bastion && length(var.admin_cidr_blocks) > 0 ? 1 : 0
  type              = "ingress"
  security_group_id = aws_security_group.bastion[0].id
  from_port         = 22
  to_port           = 22
  protocol          = "tcp"
  cidr_blocks       = var.admin_cidr_blocks
  description       = "SSH from admin CIDRs"
}

resource "aws_security_group_rule" "bastion_egress_app_ssh" {
  count                    = var.enable_bastion ? 1 : 0
  type                     = "egress"
  security_group_id        = aws_security_group.bastion[0].id
  from_port                = 22
  to_port                  = 22
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.app.id
  description              = "SSH to app"
}

resource "aws_security_group_rule" "bastion_egress_https" {
  count             = var.enable_bastion ? 1 : 0
  type              = "egress"
  security_group_id = aws_security_group.bastion[0].id
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  description       = "HTTPS for updates"
}

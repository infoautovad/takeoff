locals {
  app_ami = var.app_ami_id != "" ? var.app_ami_id : data.aws_ami.al2023.id

  user_data = <<-EOF
    #!/bin/bash
    set -euo pipefail
    dnf update -y
    dnf install -y python3.12 python3.12-pip git amazon-cloudwatch-agent amazon-ssm-agent
    systemctl enable --now amazon-ssm-agent

    mkdir -p /opt/autovad
    cat >/opt/autovad/fetch-secrets.sh <<'SCRIPT'
    #!/bin/bash
    set -euo pipefail
    REGION="${var.aws_region}"
    aws secretsmanager get-secret-value --secret-id ${aws_secretsmanager_secret.app.name} --region "$REGION" --query SecretString --output text > /opt/autovad/app-secrets.json
    aws secretsmanager get-secret-value --secret-id ${aws_secretsmanager_secret.db.name} --region "$REGION" --query SecretString --output text > /opt/autovad/db-secrets.json
    SCRIPT
    chmod +x /opt/autovad/fetch-secrets.sh

    # Placeholder app boot: replace with your CI/CD deploy of FastAPI
    cat >/etc/systemd/system/autovad.service <<'UNIT'
    [Unit]
    Description=AutoVAD API
    After=network.target

    [Service]
    Type=simple
    WorkingDirectory=/opt/autovad/app
    Environment=APP_ENV=${var.environment}
    Environment=AWS_REGION=${var.aws_region}
    Environment=STORAGE_BACKEND=s3
    Environment=S3_BUCKET=${aws_s3_bucket.uploads.id}
    ExecStartPre=/opt/autovad/fetch-secrets.sh
    ExecStart=/usr/bin/python3.12 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
    Restart=always
    RestartSec=5
    User=root

    [Install]
    WantedBy=multi-user.target
    UNIT

    mkdir -p /opt/autovad/app
    # Health stub until app code is deployed
    cat >/opt/autovad/app/health_stub.py <<'PY'
    from fastapi import FastAPI
    app = FastAPI()
    @app.get("/health")
    def health():
        return {"status": "ok", "service": "AutoVAD"}
    PY

    # Temporary health service so ALB becomes healthy before full deploy
    python3.12 -m pip install fastapi uvicorn
    nohup python3.12 -m uvicorn health_stub:app --app-dir /opt/autovad/app --host 0.0.0.0 --port 8000 >/var/log/autovad-health.log 2>&1 &
  EOF
}

resource "aws_instance" "app" {
  ami                    = local.app_ami
  instance_type          = var.app_instance_type
  subnet_id              = aws_subnet.private_app[0].id
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.app.name
  key_name               = var.bastion_key_name != "" ? var.bastion_key_name : null

  associate_public_ip_address = false
  user_data                   = local.user_data
  user_data_replace_on_change = true

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 40
    encrypted             = true
    kms_key_id            = aws_kms_key.main.arn
    delete_on_termination = true
  }

  monitoring = true

  tags = {
    Name = "${local.name_prefix}-app"
    Role = "api"
  }
}

resource "aws_lb_target_group_attachment" "app" {
  target_group_arn = aws_lb_target_group.app.arn
  target_id        = aws_instance.app.id
  port             = 8000
}

resource "aws_instance" "bastion" {
  count                       = var.enable_bastion ? 1 : 0
  ami                         = local.app_ami
  instance_type               = "t3.micro"
  subnet_id                   = aws_subnet.public[0].id
  vpc_security_group_ids      = [aws_security_group.bastion[0].id]
  key_name                    = var.bastion_key_name != "" ? var.bastion_key_name : null
  associate_public_ip_address = true

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 20
    encrypted   = true
    kms_key_id  = aws_kms_key.main.arn
  }

  tags = {
    Name = "${local.name_prefix}-bastion"
  }
}

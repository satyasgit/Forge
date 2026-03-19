"""
DevOps Skill: Infrastructure-as-code pattern detector.
Mirrors skills/security/sast.py — each entry is a named pattern
the DevOpsAgent pre-scans for in Dockerfile, YAML, and config files.
"""

INFRA_GAP_PATTERNS: list[dict] = [
    # ── Dockerfile ─────────────────────────────────────────────────────────────
    {
        "name": "Dockerfile missing non-root user",
        "regex": r"FROM\s+\w+(?!.*\n.*USER\s+(?!root))",
        "severity": "high",
        "category": "security",
        "file_types": ["Dockerfile"],
        "description": "Container runs as root by default — violates least-privilege principle.",
        "fix": "RUN useradd -m -u 1001 appuser\nUSER appuser",
        "why": "Root in container = root on host if container escape occurs.",
    },
    {
        "name": "Dockerfile using latest tag",
        "regex": r"FROM\s+\w+:latest",
        "severity": "high",
        "category": "reproducibility",
        "file_types": ["Dockerfile"],
        "description": "FROM :latest is unpredictable — builds break when base image updates.",
        "fix": "FROM python:3.11.9-slim",
        "why": "Pin exact versions for reproducible builds.",
    },
    {
        "name": "Dockerfile missing health check",
        "regex": r"^(?!.*HEALTHCHECK).*CMD\s+",
        "severity": "medium",
        "category": "reliability",
        "file_types": ["Dockerfile"],
        "description": "No HEALTHCHECK — orchestrator can't detect unhealthy containers.",
        "fix": "HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8000/health || exit 1",
        "why": "Without HEALTHCHECK, Kubernetes/ECS will route traffic to crashed containers.",
    },
    {
        "name": "Dockerfile ADD instead of COPY",
        "regex": r"^ADD\s+(?!http)",
        "severity": "low",
        "category": "best_practice",
        "file_types": ["Dockerfile"],
        "description": "ADD has hidden behaviour (auto-extracts archives, fetches URLs). Use COPY.",
        "fix": "COPY requirements.txt .",
        "why": "COPY is explicit — you always know what it does.",
    },
    {
        "name": "Dockerfile missing .dockerignore reference",
        "regex": r"COPY\s+\.\s+\.",
        "severity": "medium",
        "category": "security",
        "file_types": ["Dockerfile"],
        "description": "COPY . . without .dockerignore copies .env, .git, secrets into image.",
        "fix": "Create .dockerignore:\n.env\n.git\n__pycache__\n*.pyc\nnode_modules",
        "why": ".env in Docker image = credentials shipped in every container.",
    },

    # ── GitHub Actions ─────────────────────────────────────────────────────────
    {
        "name": "GitHub Actions using mutable ref",
        "regex": r"uses:\s+\w+/\w+@(?:main|master|latest|v\d+(?!\.\d))",
        "severity": "high",
        "category": "supply_chain",
        "file_types": [".yml", ".yaml"],
        "description": "Action pinned to mutable ref — supply chain attack risk.",
        "fix": "uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2",
        "why": "Mutable refs can be redirected. Pin to commit SHA.",
    },
    {
        "name": "GitHub Actions secret in run step",
        "regex": r"run:.*\$\{\{.*secrets\.\w+.*\}\}",
        "severity": "high",
        "category": "security",
        "file_types": [".yml", ".yaml"],
        "description": "Secret interpolated directly into run command — leaks in logs.",
        "fix": "Set as environment variable:\nenv:\n  MY_SECRET: ${{ secrets.MY_SECRET }}\nrun: use_secret $MY_SECRET",
        "why": "GitHub masks secrets in env vars but not in direct interpolation.",
    },
    {
        "name": "GitHub Actions missing permissions block",
        "regex": r"^jobs:\s*\n(?!.*permissions:)",
        "severity": "medium",
        "category": "security",
        "file_types": [".yml", ".yaml"],
        "description": "No explicit permissions — workflow has default broad permissions.",
        "fix": "permissions:\n  contents: read\n  packages: write",
        "why": "Least privilege: only grant what the workflow actually needs.",
    },
    {
        "name": "GitHub Actions no timeout",
        "regex": r"^\s+\w+-job:\s*\n(?!.*timeout-minutes:)",
        "severity": "low",
        "category": "reliability",
        "file_types": [".yml", ".yaml"],
        "description": "No job timeout — hung test or infinite loop burns CI minutes.",
        "fix": "timeout-minutes: 15",
        "why": "Default is 6 hours — a hanging job wastes resources for hours.",
    },

    # ── docker-compose ─────────────────────────────────────────────────────────
    {
        "name": "docker-compose hardcoded password",
        "regex": r"(?:POSTGRES_PASSWORD|MYSQL_ROOT_PASSWORD|REDIS_PASSWORD)\s*:\s*(?!\\$\{)",
        "severity": "high",
        "category": "security",
        "file_types": ["docker-compose.yml", "docker-compose.yaml"],
        "description": "Database password hardcoded in docker-compose — committed to git.",
        "fix": "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}  # from .env",
        "why": "Hardcoded passwords in version control = credential exposure.",
    },
    {
        "name": "docker-compose missing resource limits",
        "regex": r"services:\s*\n(?:(?!\s+deploy:)[\s\S])*?\n\s+\w+:",
        "severity": "low",
        "category": "reliability",
        "file_types": ["docker-compose.yml"],
        "description": "No memory/CPU limits — one runaway container can OOM the host.",
        "fix": "deploy:\n  resources:\n    limits:\n      memory: 512M\n      cpus: '0.5'",
        "why": "Without limits a memory leak takes down the entire machine.",
    },

    # ── Terraform / infra ──────────────────────────────────────────────────────
    {
        "name": "Terraform S3 bucket public access",
        "regex": r"acl\s*=\s*['\"]public-read['\"]",
        "severity": "critical",
        "category": "security",
        "file_types": [".tf"],
        "description": "S3 bucket with public-read ACL — data exposed to the internet.",
        "fix": 'acl = "private"\nblock_public_acls = true\nblock_public_policy = true',
        "why": "Public S3 bucket = data breach. Almost all S3 breaches are misconfigured ACLs.",
    },
    {
        "name": "Terraform missing state backend",
        "regex": r"terraform\s*\{(?!.*\n.*backend)",
        "severity": "high",
        "category": "collaboration",
        "file_types": [".tf"],
        "description": "No remote state backend — local state can't be shared or locked.",
        "fix": 'backend "s3" {\n  bucket = "my-tf-state"\n  key = "prod/terraform.tfstate"\n  region = "us-east-1"\n  dynamodb_table = "terraform-locks"\n}',
        "why": "Two engineers running terraform apply simultaneously will corrupt state.",
    },
]

# ── Anti-patterns in infra files ──────────────────────────────────────────────

INFRA_ANTIPATTERNS: list[dict] = [
    {
        "name": "Port 22 open to 0.0.0.0/0",
        "regex": r"0\.0\.0\.0/0|cidr_blocks\s*=\s*\[\"0\.0\.0\.0",
        "severity": "critical",
        "category": "security",
        "description": "SSH port open to the entire internet — brute force target.",
        "fix": "Restrict to VPN CIDR or use AWS Systems Manager Session Manager instead of SSH.",
    },
    {
        "name": "All ports open (0-65535)",
        "regex": r"from_port\s*=\s*0.*to_port\s*=\s*65535",
        "severity": "critical",
        "category": "security",
        "description": "Security group allows all traffic — defeats network segmentation.",
        "fix": "Only open ports your service actually uses: 443, 8000, 5432 etc.",
    },
    {
        "name": "Unencrypted RDS instance",
        "regex": r"storage_encrypted\s*=\s*false",
        "severity": "high",
        "category": "compliance",
        "description": "RDS without encryption at rest — fails SOC 2, HIPAA, GDPR requirements.",
        "fix": "storage_encrypted = true\nkms_key_id = aws_kms_key.rds.arn",
    },
    {
        "name": "Single AZ deployment",
        "regex": r"multi_az\s*=\s*false",
        "severity": "medium",
        "category": "reliability",
        "description": "RDS in single AZ — AZ outage = downtime.",
        "fix": "multi_az = true  # for production",
    },
]

# ── Environment variable checklist ────────────────────────────────────────────

ENV_VAR_CATEGORIES = {
    "required_always": [
        "ANTHROPIC_API_KEY",
        "DATABASE_URL",
        "JWT_SECRET_KEY",
        "APP_SECRET_KEY",
    ],
    "required_for_billing": [
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "STRIPE_PUBLISHABLE_KEY",
    ],
    "required_for_notifications": [
        "SENDGRID_API_KEY or SMTP_PASSWORD",
        "SLACK_BOT_TOKEN",
    ],
    "required_for_production": [
        "SENTRY_DSN",
        "ALLOWED_ORIGINS",
        "LOG_LEVEL=INFO",
        "DEBUG=false",
    ],
    "never_in_env": [
        "DATABASE_URL in client-side code",
        "Stripe SECRET key in frontend",
        "Private keys anywhere in source",
    ],
}

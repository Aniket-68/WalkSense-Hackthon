# WalkSense — EC2 Deployment Setup

## One-Time EC2 Setup

SSH into your EC2 instance and run:

```bash
# 1. Install Docker + Compose + AWS CLI
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin awscli
sudo usermod -aG docker ubuntu
newgrp docker

# 2. Clone the repo
git clone https://github.com/YOUR_ORG/WalkSense-Hackthon.git ~/WalkSense-Hackthon

# 3. Create .env from template
cd ~/WalkSense-Hackthon/Backend
cp .env.example .env
nano .env   # fill in GEMINI_API_KEY, MONGO_DB_API_KEY, JWT_ACCESS_SECRET, JWT_REFRESH_SECRET, CORS_ALLOWED_ORIGINS
```

## IAM Instance Role (EC2 → ECR pull, no access keys)

```bash
# Run from your local machine (one-time)
aws iam create-role --role-name walksense-ec2 \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam attach-role-policy --role-name walksense-ec2 \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly

aws iam create-instance-profile --instance-profile-name walksense-ec2
aws iam add-role-to-instance-profile --instance-profile-name walksense-ec2 --role-name walksense-ec2
aws ec2 associate-iam-instance-profile --instance-id i-XXXXXXXXXXXX --iam-instance-profile Name=walksense-ec2
```

## GitHub Actions Secrets Required

| Secret | Value |
|---|---|
| `AWS_ACCOUNT_ID` | `194861362156` |
| `AWS_REGION` | ECR/AWS region (example: `ap-southeast-1`) |
| `ECR_REGISTRY` | Example: `194861362156.dkr.ecr.ap-southeast-1.amazonaws.com` |
| `ECR_REPO` | Example: `walksense-hackathon-prototype` |
| `EC2_HOST` | EC2 Elastic IP address |
| `EC2_SSH_USER` | SSH username (example: `ubuntu`) |
| `EC2_SSH_PRIVATE_KEY` | Private key contents (PEM) |
| `EC2_SSH_PORT` | Optional, default `22` |
| `DOMAIN` | Your domain (e.g. `walksense.example.com`) |

## What Happens on `git push prototype-test`

1. GitHub Actions builds Docker image
2. Pushes to ECR:
   - `${ECR_REPO}:backend-<sha>` and `${ECR_REPO}:backend-latest`
3. SSHs into EC2
4. EC2 authenticates to ECR via instance role
5. Pulls backend image + starts fallback/monitoring stack (vLLM, Prometheus, Grafana)
6. Runs `docker compose -f deploy/ec2/docker-compose.ec2.yml up -d --remove-orphans`

## Manual Commands on EC2

```bash
cd ~/WalkSense-Hackthon

# First pull + start
REGISTRY="194861362156.dkr.ecr.ap-southeast-1.amazonaws.com"
aws ecr get-login-password --region ap-southeast-1 \
  | docker login --username AWS --password-stdin $REGISTRY

export BACKEND_IMAGE="$REGISTRY/walksense-hackathon-prototype:backend-latest"
export APP_ENV=production

docker compose -f deploy/ec2/docker-compose.ec2.yml pull backend
docker compose -f deploy/ec2/docker-compose.ec2.yml up -d --remove-orphans

# Check status
docker compose -f deploy/ec2/docker-compose.ec2.yml ps
docker compose -f deploy/ec2/docker-compose.ec2.yml logs -f backend
```

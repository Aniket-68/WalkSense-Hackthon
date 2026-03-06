# EC2 Deployment (GitHub Actions + ECR + Docker Compose)

This path deploys WalkSense to a plain EC2 host without ECS.

## 1) GitHub Secrets

Set these repository secrets:

- `AWS_ACCOUNT_ID` (example: `194861362156`)
- `DOMAIN` (used for frontend build arg `VITE_API_URL`)
- `EC2_HOST` (public IP/DNS of the instance)
- `EC2_SSH_USER` (for example `ubuntu`)
- `EC2_SSH_PRIVATE_KEY` (private key content for SSH)
- `EC2_SSH_PORT` (optional, defaults to `22`)

Optional GitHub variable:

- `APP_ENV` (`production` by default)

## 2) EC2 Prerequisites

On the EC2 instance, install:

- Docker Engine
- Docker Compose plugin (`docker compose`)
- AWS CLI v2
- Git

Ensure user can run docker (for example by adding user to `docker` group).

## 3) EC2 IAM Permissions

Attach an instance role that can pull from ECR:

- `ecr:GetAuthorizationToken`
- `ecr:BatchCheckLayerAvailability`
- `ecr:GetDownloadUrlForLayer`
- `ecr:BatchGetImage`

## 4) App Config on EC2

Create a runtime env file at:

- `<deploy_path>/.env` (default deploy path is `/opt/WalkSense-Hackthon`)

Populate required keys like:

- `GEMINI_API_KEY`
- `DEEPGRAM_API_KEY`
- `CARTESIA_API_KEY`
- `MONGO_DB_API_KEY`
- `JWT_ACCESS_SECRET`
- `JWT_REFRESH_SECRET`
- `CORS_ALLOWED_ORIGINS`

## 5) Run Deployment

Use GitHub Actions workflow:

- **Workflow**: `WalkSense Deploy to EC2`
- **Inputs**:
  - `branch` (default `prototype-test`)
  - `deploy_path` (default `/opt/WalkSense-Hackthon`)

The workflow:

1. Builds backend/frontend images.
2. Pushes them to ECR with SHA tag + `latest`.
3. SSHes into EC2, updates repo to selected branch.
4. Pulls new images and restarts services using `deploy/ec2/docker-compose.ec2.yml`.

#!/usr/bin/env bash
# ============================================================
# WalkSense — Bootstrap all secrets into AWS Secrets Manager
# Run once before first deployment.
# Usage: AWS_ACCOUNT_ID=123456789012 ./secrets-bootstrap.sh
# ============================================================
set -euo pipefail

REGION="us-east-1"

create_or_update() {
    local name="$1"
    local value="$2"
    local desc="$3"

    if aws secretsmanager describe-secret --secret-id "${name}" \
           --region "$REGION" &>/dev/null; then
        aws secretsmanager put-secret-value \
            --secret-id "${name}" \
            --secret-string "$value" \
            --region "$REGION"
        echo "✅ Updated: ${name}"
    else
        aws secretsmanager create-secret \
            --name "${name}" \
            --description "$desc" \
            --secret-string "$value" \
            --region "$REGION"
        echo "✅ Created: ${name}"
    fi
}

# ── Prompt for values ──────────────────────────────────────
read -rsp "GEMINI_API_KEY: "       GEMINI_KEY;       echo
read -rsp "DEEPGRAM_API_KEY: "     DEEPGRAM_KEY;     echo
read -rsp "CARTESIA_API_KEY: "     CARTESIA_KEY;     echo
read -rsp "MONGO_DB_API_KEY (URI): " MONGO_URI;      echo
read -rsp "JWT_ACCESS_SECRET: "    JWT_ACCESS;       echo
read -rsp "JWT_REFRESH_SECRET: "   JWT_REFRESH;      echo
read -rp  "CORS_ALLOWED_ORIGINS: " CORS_ORIGINS

echo ""
echo "Creating secrets in AWS Secrets Manager (region: $REGION)..."

create_or_update "GEMINI_API_KEY"       "$GEMINI_KEY"    "Google Gemini API key (VLM + LLM)"
create_or_update "DEEPGRAM_API_KEY"     "$DEEPGRAM_KEY"  "Deepgram STT API key"
create_or_update "CARTESIA_API_KEY"     "$CARTESIA_KEY"  "Cartesia TTS API key (optional)"
create_or_update "MONGO_DB_API_KEY"     "$MONGO_URI"     "MongoDB Atlas connection URI"
create_or_update "JWT_ACCESS_SECRET"    "$JWT_ACCESS"    "JWT access token signing secret"
create_or_update "JWT_REFRESH_SECRET"   "$JWT_REFRESH"   "JWT refresh token signing secret"
create_or_update "CORS_ALLOWED_ORIGINS" "$CORS_ORIGINS"  "Comma-separated allowed CORS origins"

echo ""
echo "🎉 All secrets bootstrapped."
echo "Next: Replace ACCOUNT_ID placeholders in deploy/ecs/backend-task-definition.json"

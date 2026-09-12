#!/bin/bash
# Shared configuration for the deploy scripts. No secrets in this file —
# secret VALUES live only in Secret Manager (see setup-infra.sh).
# Override anything here via environment before sourcing.

export PROJECT_ID="${MOKARA_PROJECT_ID:-mokara-prod}"
export REGION="${MOKARA_REGION:-europe-west4}"

# Artifact Registry
export AR_REPO="mokara"
export IMAGE_BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}"

# Cloud SQL
export SQL_INSTANCE="mokara-db"
export SQL_CONNECTION="${PROJECT_ID}:${REGION}:${SQL_INSTANCE}"
export DB_NAME="btc_simulator_prod"
export DB_USER="app_user"

# Storage
export BUCKET_NAME="${PROJECT_ID}-pdfs"

# Cloud Run services
export SVC_API="mokara-api"
export SVC_WORKER="mokara-worker"
export SVC_WEB="mokara-web"

# Dedicated runtime service account (created by setup-infra.sh)
export RUN_SA="mokara-run@${PROJECT_ID}.iam.gserviceaccount.com"

# Secret Manager secret names (values are set in setup-infra.sh, never here)
export SECRET_DB_PASSWORD="db-password"
export SECRET_INTERNAL_API="internal-api-secret"
export SECRET_BETTER_AUTH="better-auth-secret"
export SECRET_GEMINI="gemini-api-key"
export SECRET_GOOGLE_CLIENT="google-client-secret"
export SECRET_ADMIN_PASSWORD="admin-password"
export SECRET_DATABASE_URL="database-url"   # full pg URL for Better Auth (web)

# Public URL (set after domain mapping; used for BETTER_AUTH_URL)
export PUBLIC_URL="${MOKARA_PUBLIC_URL:-https://mokara.ai}"

# Gemini model tiers. Keys created after ~2026 can't call gemini-2.5-pro
# (the code's default) — pin the strong tier here so it survives deploys
# (deploy.sh uses --set-env-vars, which REPLACES console-set env).
export GEMINI_MODEL_STRONG="${GEMINI_MODEL_STRONG:-gemini-3.1-pro-preview}"
export GEMINI_MODEL_FAST="${GEMINI_MODEL_FAST:-gemini-2.5-flash}"

# OAuth client id (public identifier, not a secret; the secret is in
# Secret Manager). Required to deploy web.
export GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID:-}"

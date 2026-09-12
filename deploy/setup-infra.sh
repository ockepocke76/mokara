#!/bin/bash
# One-time infrastructure setup for Mokara on Google Cloud.
# Idempotent: safe to re-run; existing resources are skipped.
#
# Secrets are read from your shell environment at run time and pushed to
# Secret Manager — they are NEVER stored in this repo. Before running:
#
#   export DB_PASSWORD="$(openssl rand -hex 24)"
#   export INTERNAL_API_SECRET="$(openssl rand -hex 32)"
#   export BETTER_AUTH_SECRET="$(openssl rand -hex 32)"
#   export GEMINI_API_KEY="..."          # from AI Studio
#   export GOOGLE_CLIENT_SECRET="..."    # from Google Cloud console OAuth client
#   export ADMIN_PASSWORD="..."
#
# Usage:  ./deploy/setup-infra.sh

set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh

for var in DB_PASSWORD INTERNAL_API_SECRET BETTER_AUTH_SECRET GEMINI_API_KEY GOOGLE_CLIENT_SECRET ADMIN_PASSWORD; do
  if [ -z "${!var:-}" ]; then
    echo "ERROR: \$$var is not set (see header of this script)." >&2
    exit 1
  fi
done

echo "=== Mokara infra setup: project=$PROJECT_ID region=$REGION ==="

echo "--- Enabling APIs"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com \
  monitoring.googleapis.com \
  --project="$PROJECT_ID"

echo "--- Artifact Registry repo"
gcloud artifacts repositories describe "$AR_REPO" --location="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$AR_REPO" \
    --repository-format=docker --location="$REGION" --project="$PROJECT_ID"

echo "--- Runtime service account"
gcloud iam service-accounts describe "$RUN_SA" --project="$PROJECT_ID" >/dev/null 2>&1 || \
  gcloud iam service-accounts create mokara-run \
    --display-name="Mokara Cloud Run runtime" --project="$PROJECT_ID"

echo "--- Cloud SQL (PostgreSQL)"
if ! gcloud sql instances describe "$SQL_INSTANCE" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud sql instances create "$SQL_INSTANCE" \
    --database-version=POSTGRES_17 \
    --tier=db-g1-small \
    --region="$REGION" \
    --storage-auto-increase \
    --backup --backup-start-time=03:00 \
    --project="$PROJECT_ID"
fi
gcloud sql databases describe "$DB_NAME" --instance="$SQL_INSTANCE" --project="$PROJECT_ID" >/dev/null 2>&1 || \
  gcloud sql databases create "$DB_NAME" --instance="$SQL_INSTANCE" --project="$PROJECT_ID"
if gcloud sql users list --instance="$SQL_INSTANCE" --project="$PROJECT_ID" --format='value(name)' | grep -qx "$DB_USER"; then
  # Keep the real password in sync with the secret we're about to write —
  # a re-run with a new DB_PASSWORD must rotate both or neither.
  gcloud sql users set-password "$DB_USER" --instance="$SQL_INSTANCE" --password="$DB_PASSWORD" --project="$PROJECT_ID"
else
  gcloud sql users create "$DB_USER" --instance="$SQL_INSTANCE" --password="$DB_PASSWORD" --project="$PROJECT_ID"
fi

echo "--- GCS bucket (PDFs)"
if ! gcloud storage buckets describe "gs://$BUCKET_NAME" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$BUCKET_NAME" \
    --location="$REGION" --uniform-bucket-level-access --project="$PROJECT_ID"
fi

echo "--- Secrets"
create_secret() {
  local name="$1" value="$2"
  if gcloud secrets describe "$name" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "    $name exists — adding new version"
    printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- --project="$PROJECT_ID"
  else
    printf '%s' "$value" | gcloud secrets create "$name" --data-file=- --project="$PROJECT_ID"
  fi
}
create_secret "$SECRET_DB_PASSWORD"    "$DB_PASSWORD"
create_secret "$SECRET_INTERNAL_API"   "$INTERNAL_API_SECRET"
create_secret "$SECRET_BETTER_AUTH"    "$BETTER_AUTH_SECRET"
create_secret "$SECRET_GEMINI"         "$GEMINI_API_KEY"
create_secret "$SECRET_GOOGLE_CLIENT"  "$GOOGLE_CLIENT_SECRET"
create_secret "$SECRET_ADMIN_PASSWORD" "$ADMIN_PASSWORD"
# Full pg URL for Better Auth (unix socket through the Cloud Run SQL
# connector). The password goes into URI userinfo, so percent-encode it —
# a '/' or '+' in a raw password silently breaks pg's URL parsing.
DB_PASSWORD_ENC="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$DB_PASSWORD")"
create_secret "$SECRET_DATABASE_URL" \
  "postgresql://${DB_USER}:${DB_PASSWORD_ENC}@localhost/${DB_NAME}?host=/cloudsql/${SQL_CONNECTION}"

echo "--- IAM for runtime SA"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUN_SA" --role="roles/cloudsql.client" --condition=None >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUN_SA" --role="roles/monitoring.metricWriter" --condition=None >/dev/null
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET_NAME" \
  --member="serviceAccount:$RUN_SA" --role="roles/storage.objectAdmin" >/dev/null
for s in "$SECRET_DB_PASSWORD" "$SECRET_INTERNAL_API" "$SECRET_BETTER_AUTH" \
         "$SECRET_GEMINI" "$SECRET_GOOGLE_CLIENT" "$SECRET_ADMIN_PASSWORD" "$SECRET_DATABASE_URL"; do
  gcloud secrets add-iam-policy-binding "$s" \
    --member="serviceAccount:$RUN_SA" --role="roles/secretmanager.secretAccessor" \
    --project="$PROJECT_ID" >/dev/null
done

echo ""
echo "✅ Infra ready. Next: seed/migrate the DB (see DEPLOY.md), then ./deploy/deploy.sh all"

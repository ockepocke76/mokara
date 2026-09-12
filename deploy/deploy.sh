#!/bin/bash
# Build and deploy Mokara to Cloud Run.
#
# Usage:  ./deploy/deploy.sh [api|worker|web|all]
#
# Requires setup-infra.sh to have run once (secrets, SQL, bucket, SA).
# Images build remotely via Cloud Build; no local Docker needed.
#
# Topology (decided in W7, see PORT_PLAN.md):
#   mokara-api    — FastAPI, request/response only; scale to zero
#   mokara-worker — same image, `python worker.py`; polls BACKGROUND_JOBS.
#                   min=1 + CPU always allocated (it gets no HTTP traffic,
#                   so request-based throttling would starve running jobs).
#                   Scale under load by raising max-instances — the queue's
#                   FOR UPDATE SKIP LOCKED makes concurrent workers safe.
#   mokara-web    — Next.js BFF, the only public entrypoint

set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh
cd ..

TARGET="${1:-all}"
GIT_SHA="$(git rev-parse --short HEAD)"

API_IMAGE="${IMAGE_BASE}/api:${GIT_SHA}"
WEB_IMAGE="${IMAGE_BASE}/web:${GIT_SHA}"

POSTGRES_ENV="POSTGRES_HOST=/cloudsql/${SQL_CONNECTION},POSTGRES_DB=${DB_NAME},POSTGRES_USER=${DB_USER},POSTGRES_SSLMODE=disable"
PDF_ENV="PDF_STORAGE_BACKEND=gcs,GCS_BUCKET_NAME=${BUCKET_NAME}"

build_api() {
  echo "--- Building api/worker image ($API_IMAGE)"
  gcloud builds submit api --tag "$API_IMAGE" --project="$PROJECT_ID"
}

build_web() {
  echo "--- Building web image ($WEB_IMAGE)"
  gcloud builds submit web --tag "$WEB_IMAGE" --project="$PROJECT_ID"
}

deploy_api() {
  echo "--- Deploying $SVC_API"
  # Reachable over HTTPS but useless without the internal secret header
  # (verify_internal_secret on every endpoint). Hardening to IAM/ingress
  # controls is a documented follow-up in DEPLOY.md.
  gcloud run deploy "$SVC_API" \
    --image "$API_IMAGE" \
    --region "$REGION" --project="$PROJECT_ID" \
    --service-account "$RUN_SA" \
    --allow-unauthenticated \
    --add-cloudsql-instances "$SQL_CONNECTION" \
    --set-env-vars "$POSTGRES_ENV,$PDF_ENV" \
    --set-secrets "POSTGRES_PASSWORD=${SECRET_DB_PASSWORD}:latest,INTERNAL_API_SECRET=${SECRET_INTERNAL_API}:latest,GEMINI_API_KEY=${SECRET_GEMINI}:latest,ADMIN_PASSWORD=${SECRET_ADMIN_PASSWORD}:latest" \
    --memory 1Gi --cpu 1 \
    --timeout 300 \
    --min-instances 0 --max-instances 10
}

deploy_worker() {
  echo "--- Deploying $SVC_WORKER"
  gcloud run deploy "$SVC_WORKER" \
    --image "$API_IMAGE" \
    --command python --args worker.py \
    --region "$REGION" --project="$PROJECT_ID" \
    --service-account "$RUN_SA" \
    --no-allow-unauthenticated \
    --add-cloudsql-instances "$SQL_CONNECTION" \
    --set-env-vars "$POSTGRES_ENV,$PDF_ENV" \
    --set-secrets "POSTGRES_PASSWORD=${SECRET_DB_PASSWORD}:latest,GEMINI_API_KEY=${SECRET_GEMINI}:latest" \
    --memory 2Gi --cpu 2 \
    --no-cpu-throttling \
    --min-instances 1 --max-instances 1
}

deploy_web() {
  echo "--- Deploying $SVC_WEB"
  local api_url
  api_url="$(gcloud run services describe "$SVC_API" --region "$REGION" --project="$PROJECT_ID" --format='value(status.url)')"
  gcloud run deploy "$SVC_WEB" \
    --image "$WEB_IMAGE" \
    --region "$REGION" --project="$PROJECT_ID" \
    --service-account "$RUN_SA" \
    --allow-unauthenticated \
    --add-cloudsql-instances "$SQL_CONNECTION" \
    --set-env-vars "API_URL=${api_url},BETTER_AUTH_URL=${PUBLIC_URL},GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID:?export GOOGLE_CLIENT_ID (not a secret, but env-provided)}" \
    --set-secrets "INTERNAL_API_SECRET=${SECRET_INTERNAL_API}:latest,BETTER_AUTH_SECRET=${SECRET_BETTER_AUTH}:latest,GOOGLE_CLIENT_SECRET=${SECRET_GOOGLE_CLIENT}:latest,DATABASE_URL=${SECRET_DATABASE_URL}:latest" \
    --memory 512Mi --cpu 1 \
    --min-instances 0 --max-instances 10
}

case "$TARGET" in
  api)    build_api && deploy_api ;;
  worker) build_api && deploy_worker ;;
  web)    build_web && deploy_web ;;
  all)
    build_api
    build_web
    deploy_api
    deploy_worker
    deploy_web
    ;;
  *) echo "Usage: $0 [api|worker|web|all]" >&2; exit 1 ;;
esac

echo ""
echo "✅ Done. Smoke-test checklist: deploy/DEPLOY.md §6"

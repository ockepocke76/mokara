#!/bin/bash
# Build and deploy Mokara to Cloud Run.
#
# Usage:  ./deploy/deploy.sh [api|worker|web|all]
#
# Requires setup-infra.sh to have run once (secrets, SQL, bucket, SA).
# Images build remotely via Cloud Build; no local Docker needed. Source
# uploads are filtered by api/.gcloudignore and web/.gcloudignore — the
# .dockerignore files only govern the build INSIDE Cloud Build.
#
# Topology rationale: deploy/DEPLOY.md. Short version: worker is its own
# always-on service; api also runs unthrottled with min=1 for now because
# W5 strategy generation executes in an api daemon thread (see DEPLOY.md
# follow-ups for the queue-based fix that lifts this).

set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh
cd ..

TARGET="${1:-all}"
case "$TARGET" in api|worker|web|all) ;; *) echo "Usage: $0 [api|worker|web|all]" >&2; exit 1 ;; esac

# Fail on missing inputs before the first multi-minute build, not after.
if [ "$TARGET" = "web" ] || [ "$TARGET" = "all" ]; then
  : "${GOOGLE_CLIENT_ID:?export GOOGLE_CLIENT_ID (public OAuth client id) before deploying web}"
fi

GIT_SHA="$(git rev-parse --short HEAD)"

API_IMAGE="${IMAGE_BASE}/api:${GIT_SHA}"
WEB_IMAGE="${IMAGE_BASE}/web:${GIT_SHA}"

POSTGRES_ENV="POSTGRES_HOST=/cloudsql/${SQL_CONNECTION},POSTGRES_DB=${DB_NAME},POSTGRES_USER=${DB_USER},POSTGRES_SSLMODE=disable"
PDF_ENV="PDF_STORAGE_BACKEND=gcs,GCS_BUCKET_NAME=${BUCKET_NAME}"
GEMINI_ENV="GEMINI_MODEL_STRONG=${GEMINI_MODEL_STRONG},GEMINI_MODEL_FAST=${GEMINI_MODEL_FAST}"
MONITORING_ENV="GCP_MONITORING_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION}"

# Skip a Cloud Build when this git SHA's image already exists (api and
# worker share one image; FORCE_BUILD=1 overrides).
have_image() {
  [ "${FORCE_BUILD:-0}" != "1" ] && \
    gcloud artifacts docker images describe "$1" --project="$PROJECT_ID" >/dev/null 2>&1
}

build_api() {
  if have_image "$API_IMAGE"; then echo "--- api image for $GIT_SHA exists, skipping build"; return; fi
  echo "--- Building api/worker image ($API_IMAGE)"
  gcloud builds submit api --tag "$API_IMAGE" --project="$PROJECT_ID"
}

build_web() {
  if have_image "$WEB_IMAGE"; then echo "--- web image for $GIT_SHA exists, skipping build"; return; fi
  echo "--- Building web image ($WEB_IMAGE)"
  gcloud builds submit web --tag "$WEB_IMAGE" --project="$PROJECT_ID"
}

deploy_api() {
  echo "--- Deploying $SVC_API"
  # HTTPS-reachable; business endpoints require the internal secret header
  # and DISABLE_API_DOCS removes /docs + /openapi.json ( /, /healthz stay
  # open for probes). IAM/ingress hardening: DEPLOY.md follow-ups.
  # min=1 + no-cpu-throttling keeps the W5 strategy-generation daemon
  # threads alive (request-based throttling would freeze them mid-run).
  gcloud run deploy "$SVC_API" \
    --image "$API_IMAGE" \
    --region "$REGION" --project="$PROJECT_ID" \
    --service-account "$RUN_SA" \
    --allow-unauthenticated \
    --add-cloudsql-instances "$SQL_CONNECTION" \
    --set-env-vars "$POSTGRES_ENV,$PDF_ENV,$GEMINI_ENV,$MONITORING_ENV,DISABLE_API_DOCS=1" \
    --set-secrets "POSTGRES_PASSWORD=${SECRET_DB_PASSWORD}:latest,INTERNAL_API_SECRET=${SECRET_INTERNAL_API}:latest,GEMINI_API_KEY=${SECRET_GEMINI}:latest,ADMIN_PASSWORD=${SECRET_ADMIN_PASSWORD}:latest" \
    --memory 1Gi --cpu 1 \
    --timeout 300 \
    --no-cpu-throttling \
    --min-instances 1 --max-instances 10
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
    --set-env-vars "$POSTGRES_ENV,$PDF_ENV,$GEMINI_ENV,$MONITORING_ENV" \
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
    --set-env-vars "API_URL=${api_url},BETTER_AUTH_URL=${PUBLIC_URL},GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}" \
    --set-secrets "INTERNAL_API_SECRET=${SECRET_INTERNAL_API}:latest,BETTER_AUTH_SECRET=${SECRET_BETTER_AUTH}:latest,GOOGLE_CLIENT_SECRET=${SECRET_GOOGLE_CLIENT}:latest,DATABASE_URL=${SECRET_DATABASE_URL}:latest" \
    --memory 512Mi --cpu 1 \
    --min-instances 0 --max-instances 10
}

case "$TARGET" in
  api)    build_api; deploy_api ;;
  worker) build_api; deploy_worker ;;
  web)    build_web; deploy_web ;;
  all)
    # The two builds share nothing — run them in parallel.
    build_api & pid_api=$!
    build_web & pid_web=$!
    wait "$pid_api" "$pid_web"
    deploy_api
    deploy_worker
    deploy_web
    ;;
esac

echo ""
echo "✅ Done. Smoke-test checklist: deploy/DEPLOY.md §6"

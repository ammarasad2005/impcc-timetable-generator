#!/usr/bin/env bash
# Deploy the CP-SAT backend to Google Cloud Run (free-tier friendly).
#
# Requirements: gcloud CLI installed + authenticated (gcloud auth login),
#               a project with billing enabled (required for Cloud Run).
#
# Usage:  PROJECT_ID=your-project-id ./deploy.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID to your GCP project id}"
REGION="${REGION:-us-central1}"          # free tier is priced on us-central1
SERVICE="${SERVICE:-impcc-cp-sat}"

gcloud config set project "$PROJECT_ID"

gcloud run deploy "$SERVICE" \
  --source . \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --cpu 2 \
  --memory 2Gi \
  --max-instances 3 \
  --min-instances 0 \
  --timeout 300

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)')"
echo
echo "✅ Deployed: $URL"
echo "   Health check:  curl $URL/health"
echo "   Set this URL as API_URL (or window.IMPCC_API_URL) in the frontend."

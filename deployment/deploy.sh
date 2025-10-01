#!/bin/bash

# Deployment script for GitHub Stats Collector Cloud Function
# This script deploys the Cloud Function and sets up Cloud Scheduler

set -e

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project)}"
REGION="${GCP_REGION:-us-central1}"
FUNCTION_NAME="${FUNCTION_NAME:-github-stats-collector}"
RUNTIME="python311"
ENTRY_POINT="collect_github_stats"
MEMORY="${MEMORY:-512MB}"
TIMEOUT="${TIMEOUT:-540s}"
MAX_INSTANCES="${MAX_INSTANCES:-1}"

# Scheduler configuration
SCHEDULE="${SCHEDULE:-0 * * * *}"  # Every hour
SCHEDULER_NAME="${SCHEDULER_NAME:-github-stats-hourly}"
TIME_ZONE="${TIME_ZONE:-America/Los_Angeles}"

# Required environment variables
GITHUB_TOKEN="${GITHUB_TOKEN}"
GITHUB_ORG="${GITHUB_ORG:-askscio}"
BIGQUERY_DATASET_ID="${BIGQUERY_DATASET_ID:-github_stats}"
GCS_BUCKET_NAME="${GCS_BUCKET_NAME:-github-stats-data}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}GitHub Stats Collector - Cloud Function Deployment${NC}"
echo "=================================================="
echo ""

# Validate required variables
if [ -z "$GITHUB_TOKEN" ]; then
    echo -e "${RED}Error: GITHUB_TOKEN environment variable is required${NC}"
    exit 1
fi

if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}Error: Could not determine GCP project ID${NC}"
    echo "Set GCP_PROJECT_ID environment variable or configure gcloud"
    exit 1
fi

echo "Configuration:"
echo "  Project ID: $PROJECT_ID"
echo "  Region: $REGION"
echo "  Function Name: $FUNCTION_NAME"
echo "  Runtime: $RUNTIME"
echo "  Memory: $MEMORY"
echo "  Timeout: $TIMEOUT"
echo "  Schedule: $SCHEDULE"
echo "  Organization: $GITHUB_ORG"
echo ""

# Navigate to cloud_function directory
cd "$(dirname "$0")/../cloud_function"

# Copy necessary modules
echo -e "${YELLOW}Preparing deployment package...${NC}"
mkdir -p modules utils
cp ../config.py .
cp ../modules/*.py modules/
cp ../utils/*.py utils/

echo -e "${YELLOW}Deploying Cloud Function...${NC}"

# Deploy the function
gcloud functions deploy "$FUNCTION_NAME" \
    --gen2 \
    --runtime="$RUNTIME" \
    --region="$REGION" \
    --source=. \
    --entry-point="$ENTRY_POINT" \
    --trigger-http \
    --allow-unauthenticated \
    --memory="$MEMORY" \
    --timeout="$TIMEOUT" \
    --max-instances="$MAX_INSTANCES" \
    --set-env-vars="GITHUB_TOKEN=$GITHUB_TOKEN,GITHUB_ORG=$GITHUB_ORG,BIGQUERY_PROJECT_ID=$PROJECT_ID,BIGQUERY_DATASET_ID=$BIGQUERY_DATASET_ID,GCS_BUCKET_NAME=$GCS_BUCKET_NAME,PERSIST_TO_GCS=true" \
    --project="$PROJECT_ID"

# Get the function URL
FUNCTION_URL=$(gcloud functions describe "$FUNCTION_NAME" \
    --region="$REGION" \
    --gen2 \
    --format='value(serviceConfig.uri)' \
    --project="$PROJECT_ID")

echo -e "${GREEN}✓ Cloud Function deployed successfully${NC}"
echo "  URL: $FUNCTION_URL"
echo ""

# Create or update Cloud Scheduler job
echo -e "${YELLOW}Setting up Cloud Scheduler...${NC}"

# Check if scheduler job exists
if gcloud scheduler jobs describe "$SCHEDULER_NAME" --location="$REGION" --project="$PROJECT_ID" &>/dev/null; then
    echo "Updating existing scheduler job..."
    gcloud scheduler jobs update http "$SCHEDULER_NAME" \
        --location="$REGION" \
        --schedule="$SCHEDULE" \
        --uri="$FUNCTION_URL" \
        --http-method=GET \
        --time-zone="$TIME_ZONE" \
        --project="$PROJECT_ID"
else
    echo "Creating new scheduler job..."
    gcloud scheduler jobs create http "$SCHEDULER_NAME" \
        --location="$REGION" \
        --schedule="$SCHEDULE" \
        --uri="$FUNCTION_URL" \
        --http-method=GET \
        --time-zone="$TIME_ZONE" \
        --project="$PROJECT_ID"
fi

echo -e "${GREEN}✓ Cloud Scheduler configured successfully${NC}"
echo ""

# Clean up temporary files
rm -rf modules utils config.py

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo "1. Test the function manually:"
echo "   curl $FUNCTION_URL"
echo ""
echo "2. View logs:"
echo "   gcloud functions logs read $FUNCTION_NAME --region=$REGION --gen2"
echo ""
echo "3. View scheduler jobs:"
echo "   gcloud scheduler jobs list --location=$REGION"
echo ""
echo "4. Trigger manually:"
echo "   gcloud scheduler jobs run $SCHEDULER_NAME --location=$REGION"
echo ""
echo "5. Monitor BigQuery:"
echo "   bq query --use_legacy_sql=false 'SELECT COUNT(*) FROM \`$PROJECT_ID.$BIGQUERY_DATASET_ID.pull_requests\`'"
echo ""

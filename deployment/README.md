# Deployment

This directory contains deployment scripts and configurations for running GitHub Stats Collector in Google Cloud Platform.

## Quick Deploy

```bash
# Set required environment variables
export GCP_PROJECT_ID="your-project-id"
export GITHUB_TOKEN="ghp_your_github_token"
export GITHUB_ORG="askscio"

# Run deployment script
chmod +x deploy.sh
./deploy.sh
```

This deploys:
- Cloud Function (Python 3.11, Gen 2)
- Cloud Scheduler (runs hourly)
- Service Account with necessary permissions
- Environment variables configured

## Terraform Deploy

```bash
cd terraform

# Copy and edit variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values

# Deploy
terraform init
terraform plan
terraform apply
```

## Files

- **`deploy.sh`**: Bash script for quick deployment
- **`terraform/main.tf`**: Terraform configuration
- **`terraform/terraform.tfvars.example`**: Terraform variables template

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GCP_PROJECT_ID` | Yes | - | GCP Project ID |
| `GITHUB_TOKEN` | Yes | - | GitHub PAT |
| `GITHUB_ORG` | No | `askscio` | GitHub org name |
| `GCS_BUCKET_NAME` | No | `github-stats-data` | GCS bucket |
| `SCHEDULE` | No | `0 * * * *` | Cron schedule |
| `MEMORY` | No | `512MB` | Function memory |
| `TIMEOUT` | No | `540s` | Function timeout |

### Schedule Examples

```bash
# Every hour
export SCHEDULE="0 * * * *"

# Every 2 hours
export SCHEDULE="0 */2 * * *"

# Every 6 hours
export SCHEDULE="0 */6 * * *"

# Daily at 2 AM
export SCHEDULE="0 2 * * *"

# Weekdays at 9 AM
export SCHEDULE="0 9 * * 1-5"
```

## Testing

```bash
# Get function URL
FUNCTION_URL=$(gcloud functions describe github-stats-collector \
    --region=us-central1 \
    --gen2 \
    --format='value(serviceConfig.uri)')

# Test manually
curl $FUNCTION_URL

# View logs
gcloud functions logs read github-stats-collector --region=us-central1 --gen2

# Trigger scheduler
gcloud scheduler jobs run github-stats-hourly --location=us-central1
```

## Monitoring

```bash
# View function metrics
gcloud monitoring dashboards list

# View logs
gcloud functions logs read github-stats-collector \
    --region=us-central1 \
    --gen2 \
    --limit=50

# Check BigQuery data
bq query --use_legacy_sql=false \
'SELECT COUNT(*) FROM `PROJECT.github_stats.pull_requests`'
```

## Updating

```bash
# Update function code
./deploy.sh

# Update environment variables
gcloud functions deploy github-stats-collector \
    --region=us-central1 \
    --update-env-vars=MAX_WORKERS=20

# Update schedule
gcloud scheduler jobs update http github-stats-hourly \
    --location=us-central1 \
    --schedule="0 */2 * * *"
```

## Cleanup

```bash
# Delete function
gcloud functions delete github-stats-collector --region=us-central1 --gen2

# Delete scheduler
gcloud scheduler jobs delete github-stats-hourly --location=us-central1

# Delete with Terraform
cd terraform
terraform destroy
```

## Documentation

See [`../DEPLOYMENT.md`](../DEPLOYMENT.md) for complete deployment guide.


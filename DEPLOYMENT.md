# Cloud Deployment Guide

Deploy GitHub Stats Collector as a Cloud Function with Cloud Scheduler for automatic hourly execution.

## Features

- ✅ **Hourly Collection**: Runs every hour automatically via Cloud Scheduler
- ✅ **Deduplication**: MERGE-based upserts prevent duplicate data
- ✅ **Serverless**: No infrastructure to manage
- ✅ **Auto-scaling**: Scales automatically with workload
- ✅ **Cost-effective**: Pay only for execution time
- ✅ **Monitoring**: Built-in logging and monitoring

## Architecture

```
Cloud Scheduler → Cloud Function → GitHub API → GCS → BigQuery
     (Hourly)      (Serverless)                 ↓
                                           Checkpoints
```

### Data Flow

1. **Cloud Scheduler** triggers the function every hour
2. **Cloud Function** collects data from the last 2 hours (with overlap)
3. **GitHub API** provides PR, commit, and review data
4. **GCS** stores raw data in chunked JSON files
5. **BigQuery** receives deduplicated data via MERGE statements

## Deduplication Strategy

The system prevents duplicates using **MERGE statements** (UPSERT):

- **PRs**: Unique on `(pr_number, repository, organization)`
- **Commits**: Unique on `(sha, repository, organization)`
- **Reviews**: Unique on `(review_id, repository, organization)`
- **Comments**: Unique on `(comment_id, repository, organization)`

Running the function multiple times on overlapping time windows is safe!

## Prerequisites

1. **GCP Project** with billing enabled
2. **GitHub Token** with `repo` and `read:org` permissions
3. **gcloud CLI** installed and authenticated
4. **Terraform** (optional, for Infrastructure as Code)

## Deployment Options

### Option 1: Quick Deploy (Bash Script)

Fastest way to deploy using a shell script.

#### Steps

1. **Set environment variables:**

```bash
export GCP_PROJECT_ID="your-project-id"
export GITHUB_TOKEN="ghp_your_token_here"
export GITHUB_ORG="askscio"
export GCS_BUCKET_NAME="github-stats-data"
```

2. **Run deployment script:**

```bash
chmod +x deployment/deploy.sh
./deployment/deploy.sh
```

3. **Verify deployment:**

```bash
# Test the function manually
curl https://REGION-PROJECT_ID.cloudfunctions.net/github-stats-collector

# View logs
gcloud functions logs read github-stats-collector --region=us-central1 --gen2

# Check scheduler
gcloud scheduler jobs list --location=us-central1
```

#### Configuration Options

The deployment script accepts these environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `GCP_PROJECT_ID` | GCP Project ID | (auto-detect) |
| `GCP_REGION` | Deployment region | `us-central1` |
| `FUNCTION_NAME` | Cloud Function name | `github-stats-collector` |
| `SCHEDULE` | Cron schedule | `0 * * * *` (hourly) |
| `SCHEDULER_NAME` | Scheduler job name | `github-stats-hourly` |
| `MEMORY` | Function memory | `512MB` |
| `TIMEOUT` | Function timeout | `540s` (9 min) |
| `MAX_INSTANCES` | Max concurrent instances | `1` |

Example with custom settings:

```bash
export MEMORY="1GB"
export SCHEDULE="0 */2 * * *"  # Every 2 hours
./deployment/deploy.sh
```

### Option 2: Terraform (Infrastructure as Code)

Use Terraform for reproducible, version-controlled deployments.

#### Steps

1. **Navigate to Terraform directory:**

```bash
cd deployment/terraform
```

2. **Create `terraform.tfvars`:**

```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
```

```hcl
project_id = "your-gcp-project-id"
region     = "us-central1"

github_token = "ghp_your_github_token_here"
github_org   = "askscio"

bigquery_dataset_id = "github_stats"
gcs_bucket_name     = "github-stats-data"

schedule  = "0 * * * *"  # Every hour
time_zone = "America/Los_Angeles"
```

3. **Initialize Terraform:**

```bash
terraform init
```

4. **Review deployment plan:**

```bash
terraform plan
```

5. **Deploy:**

```bash
terraform apply
```

6. **View outputs:**

```bash
terraform output
```

#### Terraform Outputs

After deployment, Terraform provides:

- `function_url`: The Cloud Function endpoint URL
- `function_name`: Name of the deployed function
- `scheduler_name`: Name of the scheduler job
- `service_account_email`: Service account email
- `data_bucket`: GCS bucket for data storage

### Option 3: Manual Deployment

Deploy step-by-step using gcloud commands.

#### 1. Enable Required APIs

```bash
gcloud services enable cloudfunctions.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable bigquery.googleapis.com
gcloud services enable storage-api.googleapis.com
```

#### 2. Create Service Account

```bash
gcloud iam service-accounts create github-stats-collector \
    --display-name="GitHub Stats Collector"

# Grant permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:github-stats-collector@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:github-stats-collector@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/bigquery.jobUser"
```

#### 3. Create GCS Bucket

```bash
gsutil mb -l us-central1 gs://github-stats-data

# Grant access to service account
gsutil iam ch serviceAccount:github-stats-collector@YOUR_PROJECT_ID.iam.gserviceaccount.com:roles/storage.objectAdmin \
    gs://github-stats-data
```

#### 4. Deploy Cloud Function

```bash
cd cloud_function

# Copy modules
mkdir -p modules utils
cp ../config.py .
cp ../modules/*.py modules/
cp ../utils/*.py utils/

# Deploy
gcloud functions deploy github-stats-collector \
    --gen2 \
    --runtime=python311 \
    --region=us-central1 \
    --source=. \
    --entry-point=collect_github_stats \
    --trigger-http \
    --allow-unauthenticated \
    --memory=512MB \
    --timeout=540s \
    --max-instances=1 \
    --service-account=github-stats-collector@YOUR_PROJECT_ID.iam.gserviceaccount.com \
    --set-env-vars="GITHUB_TOKEN=ghp_xxx,GITHUB_ORG=askscio,BIGQUERY_PROJECT_ID=YOUR_PROJECT_ID,BIGQUERY_DATASET_ID=github_stats,GCS_BUCKET_NAME=github-stats-data,PERSIST_TO_GCS=true"

# Cleanup
rm -rf modules utils config.py
```

#### 5. Create Cloud Scheduler Job

```bash
# Get function URL
FUNCTION_URL=$(gcloud functions describe github-stats-collector \
    --region=us-central1 \
    --gen2 \
    --format='value(serviceConfig.uri)')

# Create scheduler job
gcloud scheduler jobs create http github-stats-hourly \
    --location=us-central1 \
    --schedule="0 * * * *" \
    --uri="$FUNCTION_URL" \
    --http-method=GET \
    --time-zone="America/Los_Angeles"
```

## Configuration

### Schedule Patterns

Cloud Scheduler uses Unix cron format:

```bash
# Every hour
"0 * * * *"

# Every 2 hours
"0 */2 * * *"

# Every 6 hours
"0 */6 * * *"

# Every day at 2 AM
"0 2 * * *"

# Every 15 minutes
"*/15 * * * *"

# Weekdays at 9 AM
"0 9 * * 1-5"
```

### Time Zones

Common time zones:

- `America/Los_Angeles` (Pacific)
- `America/New_York` (Eastern)
- `America/Chicago` (Central)
- `UTC`
- `Europe/London`

Full list: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones

### Memory and Timeout

Adjust based on organization size:

| Organization Size | Memory | Timeout |
|-------------------|--------|---------|
| Small (< 10 repos) | 256MB | 300s (5 min) |
| Medium (10-50 repos) | 512MB | 540s (9 min) |
| Large (50+ repos) | 1GB | 540s (9 min) |

## Testing

### Manual Trigger

Trigger the function manually to test:

```bash
# Via gcloud
gcloud scheduler jobs run github-stats-hourly --location=us-central1

# Via curl
curl https://REGION-PROJECT_ID.cloudfunctions.net/github-stats-collector
```

### View Logs

```bash
# Recent logs
gcloud functions logs read github-stats-collector --region=us-central1 --gen2

# Stream logs in real-time
gcloud functions logs read github-stats-collector --region=us-central1 --gen2 --limit=50 --follow

# Logs for specific execution
gcloud functions logs read github-stats-collector \
    --region=us-central1 \
    --gen2 \
    --start-time="2025-01-01T00:00:00Z"
```

### Verify Data

```bash
# Check BigQuery
bq query --use_legacy_sql=false '
SELECT 
  repository,
  COUNT(*) as pr_count,
  MAX(updated_at) as last_update
FROM `YOUR_PROJECT.github_stats.pull_requests`
GROUP BY repository
ORDER BY pr_count DESC
'

# Check GCS
gsutil ls gs://github-stats-data/askscio/
```

## Monitoring

### Cloud Monitoring Metrics

Key metrics to monitor:

1. **Execution Count**: Number of function invocations
2. **Execution Time**: Duration of each execution
3. **Error Rate**: Failed executions
4. **Memory Usage**: Peak memory usage
5. **Active Instances**: Number of concurrent instances

### Set Up Alerts

Create alerts for:

```bash
# Function failures
gcloud alpha monitoring policies create \
    --notification-channels=CHANNEL_ID \
    --display-name="GitHub Collector Failures" \
    --condition-display-name="Error rate > 10%" \
    --condition-threshold-value=0.1 \
    --condition-threshold-duration=300s \
    --condition-filter='resource.type="cloud_function"
        AND resource.labels.function_name="github-stats-collector"
        AND metric.type="cloudfunctions.googleapis.com/function/execution_count"
        AND metric.labels.status="error"'
```

### BigQuery Monitoring

Track data freshness:

```sql
-- Check last update time per repository
SELECT 
  repository,
  MAX(updated_at) as last_update,
  TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(updated_at), HOUR) as hours_since_update
FROM `YOUR_PROJECT.github_stats.pull_requests`
GROUP BY repository
ORDER BY hours_since_update DESC
```

## Cost Estimation

### Cloud Function Costs

Based on 1 hourly execution (730/month):

| Component | Usage | Monthly Cost |
|-----------|-------|--------------|
| Invocations | 730 | $0.00 (free tier) |
| Compute (512MB, 2min avg) | 1,460 GB-seconds | ~$0.02 |
| Networking | Minimal | ~$0.01 |

**Total: ~$0.03/month**

### Associated Costs

| Service | Usage | Monthly Cost |
|---------|-------|--------------|
| GCS Storage | 50 GB | ~$1.00 |
| BigQuery Storage | 10 GB | ~$0.20 |
| BigQuery Queries | 1 GB scanned | $0.00 (free tier) |
| Cloud Scheduler | 730 jobs | $0.00 (free tier) |

**Total: ~$1.25/month**

## Troubleshooting

### Function Fails to Deploy

**Error: Insufficient permissions**

```bash
# Grant Cloud Build permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member=serviceAccount:YOUR_PROJECT_NUMBER@cloudbuild.gserviceaccount.com \
    --role=roles/cloudfunctions.admin
```

**Error: Python dependency conflict**

Check `cloud_function/requirements.txt` for version compatibility.

### Function Times Out

**Increase timeout:**

```bash
gcloud functions deploy github-stats-collector \
    --region=us-central1 \
    --update-env-vars=TIMEOUT=540s \
    --timeout=540s
```

**Or reduce scope:**

```bash
# Set MAX_WORKERS to reduce parallelism
gcloud functions deploy github-stats-collector \
    --region=us-central1 \
    --update-env-vars=MAX_WORKERS=5
```

### Duplicate Data

The system uses MERGE statements to prevent duplicates. If you see duplicates:

1. Check that the function is using the latest code
2. Verify BigQuery table has the expected schema
3. Run deduplication query:

```sql
-- Deduplicate pull_requests table
CREATE OR REPLACE TABLE `YOUR_PROJECT.github_stats.pull_requests` AS
SELECT * EXCEPT(row_num)
FROM (
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY pr_number, repository, organization 
      ORDER BY updated_at DESC
    ) as row_num
  FROM `YOUR_PROJECT.github_stats.pull_requests`
)
WHERE row_num = 1;
```

### Rate Limit Errors

If hitting GitHub rate limits:

1. Reduce collection frequency (every 2 hours instead of 1)
2. Increase `MAX_WORKERS` limit (slows down requests)
3. Split collection across multiple functions (by repository)

## Advanced Configuration

### Multiple Entry Points

The Cloud Function includes 3 entry points:

1. **`collect_github_stats`** (default): Simple HTTP trigger
2. **`collect_github_stats_pubsub`**: Pub/Sub trigger
3. **`manual_trigger`**: HTTP with custom parameters

Deploy additional functions:

```bash
gcloud functions deploy github-stats-manual \
    --gen2 \
    --runtime=python311 \
    --region=us-central1 \
    --source=cloud_function \
    --entry-point=manual_trigger \
    --trigger-http \
    --allow-unauthenticated
```

Use manual trigger:

```bash
curl "https://FUNCTION_URL/manual_trigger?hours=24&repos=frontend,backend"
```

### Environment-Specific Deployments

Deploy separate functions for dev/staging/prod:

```bash
# Development
gcloud functions deploy github-stats-dev \
    --set-env-vars="GITHUB_ORG=askscio-dev,BIGQUERY_DATASET_ID=github_stats_dev"

# Production
gcloud functions deploy github-stats-prod \
    --set-env-vars="GITHUB_ORG=askscio,BIGQUERY_DATASET_ID=github_stats"
```

## Updating the Function

### Update Code

```bash
cd deployment
./deploy.sh
```

This redeploys with the latest code.

### Update Environment Variables

```bash
gcloud functions deploy github-stats-collector \
    --region=us-central1 \
    --update-env-vars=MAX_WORKERS=20,GCS_CHUNK_SIZE=200
```

### Update Schedule

```bash
gcloud scheduler jobs update http github-stats-hourly \
    --location=us-central1 \
    --schedule="0 */2 * * *"  # Every 2 hours
```

## Cleanup

### Delete Everything

```bash
# Delete function
gcloud functions delete github-stats-collector --region=us-central1 --gen2

# Delete scheduler job
gcloud scheduler jobs delete github-stats-hourly --location=us-central1

# Delete GCS bucket
gsutil rm -r gs://github-stats-data

# Delete service account
gcloud iam service-accounts delete github-stats-collector@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

### Terraform Cleanup

```bash
cd deployment/terraform
terraform destroy
```

## Best Practices

1. **Use Terraform**: Version control your infrastructure
2. **Set Up Monitoring**: Create alerts for failures
3. **Review Logs**: Regularly check execution logs
4. **Monitor Costs**: Use Cloud Billing reports
5. **Test Changes**: Deploy to dev environment first
6. **Document Changes**: Keep deployment notes
7. **Regular Backups**: Export BigQuery tables periodically

## Support

For issues or questions:

1. Check logs: `gcloud functions logs read github-stats-collector --region=us-central1 --gen2`
2. Review documentation: `README.md`, `GCS_PERSISTENCE.md`
3. Open a GitHub issue

## Next Steps

After deployment:

1. **Monitor first execution**: Check logs and verify data
2. **Set up alerts**: Create Cloud Monitoring alerts
3. **Create dashboards**: Build Looker Studio dashboards
4. **Schedule reports**: Set up BigQuery scheduled queries
5. **Optimize costs**: Review and adjust resources

Congratulations! Your GitHub Stats Collector is now running automatically in the cloud! 🎉

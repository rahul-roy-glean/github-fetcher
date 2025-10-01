# Quick Start Guide

This guide will help you get started with the GitHub Stats Collector in minutes.

## Prerequisites

- Python 3.8+
- GitHub Personal Access Token
- Google Cloud Project with BigQuery enabled
- Google Cloud Service Account JSON key

## 5-Minute Setup

### 1. Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

### 2. Create Configuration

Copy the example environment file and edit it:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```bash
GITHUB_TOKEN=ghp_your_github_token_here
GITHUB_ORG=askscio
BIGQUERY_PROJECT_ID=your-gcp-project
BIGQUERY_DATASET_ID=github_stats
GCS_BUCKET_NAME=github-stats-data
PERSIST_TO_GCS=true
```

### 3. Set Google Cloud Credentials

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
```

### 4. Initialize BigQuery

```bash
python main.py init
```

This creates the dataset and all necessary tables.

### 5. Run Your First Collection

Collect data from the last 24 hours:

```bash
python main.py collect --hours 24
```

Or backfill the last 30 days:

```bash
python main.py backfill --days 30
```

## Common Use Cases

### Backfill 6 Months of Historical Data

```bash
python main.py backfill --days 180
```

This is the recommended starting point for a new setup.

### Collect Specific Repositories

```bash
python main.py backfill --days 90 --repos "frontend,backend,api"
```

### Set Up Continuous Collection

Run every 6 hours (recommended for ongoing monitoring):

```bash
python main.py scheduled --interval 6
```

Press Ctrl+C to stop.

### Custom Date Range

```bash
python main.py collect \
  --since 2025-01-01T00:00:00Z \
  --until 2025-03-31T23:59:59Z
```

## Verify Your Data

After collection, check BigQuery:

```sql
-- Count PRs by repository
SELECT 
  repository,
  COUNT(*) as pr_count,
  COUNT(DISTINCT author) as unique_authors
FROM `your-project.github_stats.pull_requests`
GROUP BY repository
ORDER BY pr_count DESC;
```

## Running in Production

### Option 1: Systemd Service (Linux)

See `README.md` for systemd service configuration.

### Option 2: Docker

```bash
docker build -t github-collector .
docker run -d \
  --name github-collector \
  --env-file .env \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json \
  -v /path/to/credentials.json:/app/credentials.json:ro \
  github-collector
```

### Option 3: Cloud Run (GCP)

Deploy as a scheduled Cloud Run job for serverless execution.

## Troubleshooting

### "GITHUB_TOKEN environment variable is required"

Make sure your `.env` file is created and the token is set.

### "Rate limit exceeded"

The system should handle this automatically. If issues persist:
1. Reduce `MAX_WORKERS` in `.env` to 5
2. Increase collection intervals

### "BigQuery permission denied"

Ensure your service account has these roles:
- BigQuery Data Editor
- BigQuery Job User

### No data collected

1. Check that your GitHub token has correct permissions (`repo`, `read:org`)
2. Verify the organization name is correct
3. Run with `-v` flag for verbose logging: `python main.py -v collect --hours 24`

## GCS Persistence Features

The collector automatically saves data to GCS before loading into BigQuery:

### View what's in GCS

```bash
python main.py gcs-summary
```

### Reload data from GCS

If you need to reprocess data:

```bash
# Wipe BigQuery data (manually via SQL)
# Then reload from GCS:
python main.py load-gcs
```

### Resume a failed collection

If a collection crashes:

```bash
# Check logs for the collection ID
python main.py resume --collection-id 2025-01-01T12:00:00+00:00
```

## Cloud Deployment (Recommended)

For production, deploy to GCP Cloud Functions for automatic hourly collection:

```bash
# Quick deploy
export GCP_PROJECT_ID="your-project-id"
export GITHUB_TOKEN="ghp_your_token_here"
./deployment/deploy.sh
```

This sets up:
- ✅ Cloud Function (serverless)
- ✅ Cloud Scheduler (runs hourly)
- ✅ Automatic deduplication
- ✅ ~$1-2/month cost

**📖 See [DEPLOYMENT.md](DEPLOYMENT.md) for details**

## Next Steps

1. **Review GCS data**: Run `gcs-summary` to see what was collected
2. **Set up cloud deployment**: Deploy to GCP for automatic hourly collection (see above)
3. **Set up monitoring**: Track collection jobs and data freshness
4. **Create dashboards**: Build visualizations in Looker/Data Studio
5. **Calculate metrics**: Use the example queries in README.md
6. **Understand GCS persistence**: Read [GCS_PERSISTENCE.md](GCS_PERSISTENCE.md)

## Support

For detailed documentation, see:
- `README.md` - Complete documentation
- `GCS_PERSISTENCE.md` - GCS persistence layer details
- `QUICKSTART.md` - This guide

For issues or questions, open a GitHub issue.

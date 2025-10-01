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

## Next Steps

1. **Set up monitoring**: Track collection jobs and data freshness
2. **Create dashboards**: Build visualizations in Looker/Data Studio
3. **Calculate metrics**: Use the example queries in README.md
4. **Schedule regular collections**: Set up the scheduled mode to run continuously

## Support

For detailed documentation, see `README.md`.

For issues or questions, open a GitHub issue.

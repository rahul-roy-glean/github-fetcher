# GitHub Stats Collector

A comprehensive data collection system for gathering GitHub repository statistics from an organization and publishing them to Google BigQuery for analysis and developer velocity metrics.

## Features

- 📊 **Complete Data Collection**: Fetches PRs, commits, reviews, review comments, and issue comments
- 🚀 **High Performance**: Parallel processing for fast data collection
- ⚡ **Rate Limit Handling**: Intelligent GitHub API rate limit management
- 📦 **BigQuery Integration**: Automatic schema creation and data publishing
- 🔄 **Incremental Updates**: Efficient incremental collection for ongoing monitoring
- 📅 **Historical Backfill**: Support for backfilling historical data (e.g., last 6 months)
- 🤖 **Bot-Aware**: Includes bot commits and properly attributes all contributions
- 🏷️ **Label Support**: Captures PR labels including size labels
- 🔍 **Flexible Filtering**: Filter by date ranges and specific repositories

## Architecture

The system is composed of three main modules:

### 1. Fetcher Module (`modules/fetcher.py`)
Handles all GitHub API interactions to fetch repository data:
- Retrieves PRs, commits, reviews, and comments
- Parallelizes API calls for better performance
- Handles missing data gracefully
- Attributes commits to authors (including bots)

### 2. Schema Module (`modules/schema.py`)
Manages BigQuery schema:
- Creates datasets and tables automatically
- Defines schemas for PRs, commits, reviews, and comments
- Sets up partitioning and clustering for query performance
- Provides a metrics table for derived analytics

### 3. Collector Module (`modules/collector.py`)
Orchestrates the collection and publishing process:
- Coordinates fetching and publishing
- Supports backfill and incremental collection
- Manages data transformation for BigQuery
- Handles batch processing efficiently

## Installation

### Prerequisites

- Python 3.8 or higher
- GitHub Personal Access Token with appropriate permissions
- Google Cloud Project with BigQuery enabled
- Google Cloud credentials configured

### Setup

1. **Clone the repository:**
```bash
git clone <repository-url>
cd github-fetcher
```

2. **Create a virtual environment:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables:**
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. **Set up Google Cloud authentication:**
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/service-account-key.json"
```

## Configuration

Create a `.env` file with the following variables:

```bash
# GitHub Configuration
GITHUB_TOKEN=ghp_your_token_here
GITHUB_ORG=askscio

# BigQuery Configuration
BIGQUERY_PROJECT_ID=your-gcp-project-id
BIGQUERY_DATASET_ID=github_stats
BIGQUERY_LOCATION=US

# Performance Configuration (Optional)
MAX_WORKERS=10
BATCH_SIZE=100
DEFAULT_LOOKBACK_DAYS=180
```

### GitHub Token Permissions

Your GitHub token needs the following scopes:
- `repo` (full control of private repositories)
- `read:org` (read organization data)

## Usage

### Initialize BigQuery Schema

Before collecting data, initialize the BigQuery dataset and tables:

```bash
python main.py init
```

### Backfill Historical Data

Backfill the last 6 months of data:

```bash
python main.py backfill --days 180
```

Backfill specific repositories:

```bash
python main.py backfill --days 90 --repos "repo1,repo2,repo3"
```

### Collect Data for a Date Range

Collect data between specific dates:

```bash
python main.py collect --since 2025-01-01T00:00:00Z --until 2025-03-31T23:59:59Z
```

Collect data from the last 12 hours:

```bash
python main.py collect --hours 12
```

Collect specific repositories:

```bash
python main.py collect --hours 24 --repos "frontend,backend"
```

### Run Scheduled Collection

Run continuous collection every 6 hours:

```bash
python main.py scheduled --interval 6
```

This will run indefinitely until stopped with Ctrl+C. Perfect for deployment as a service.

### Verbose Logging

Enable detailed logging for debugging:

```bash
python main.py -v backfill --days 30
```

## BigQuery Schema

The system creates the following tables:

### `pull_requests`
Main PR data including metadata, metrics, and state information.

### `commits`
Individual commits linked to PRs with author attribution.

### `reviews`
PR reviews with reviewer information and state.

### `review_comments`
Line-by-line review comments on code changes.

### `issue_comments`
General comments on PRs (issue-style comments).

### `metrics`
Derived metrics for developer velocity analysis (calculated separately).

All tables are partitioned by date and clustered for optimal query performance.

## Example Queries

### Developer Velocity by Author

```sql
SELECT 
  author,
  COUNT(*) as prs_created,
  SUM(CASE WHEN is_merged THEN 1 ELSE 0 END) as prs_merged,
  SUM(additions) as lines_added,
  SUM(deletions) as lines_deleted,
  AVG(review_count) as avg_reviews_received
FROM `your-project.github_stats.pull_requests`
WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  AND author_type = 'User'
GROUP BY author
ORDER BY prs_merged DESC
```

### PR Size Distribution

```sql
SELECT 
  size_label,
  COUNT(*) as pr_count,
  AVG(TIMESTAMP_DIFF(merged_at, created_at, HOUR)) as avg_time_to_merge_hours
FROM `your-project.github_stats.pull_requests`
WHERE is_merged = TRUE
  AND size_label IS NOT NULL
GROUP BY size_label
ORDER BY pr_count DESC
```

### Review Activity

```sql
SELECT 
  reviewer,
  COUNT(*) as reviews_given,
  COUNT(DISTINCT pr_number) as prs_reviewed,
  COUNT(DISTINCT repository) as repos_reviewed
FROM `your-project.github_stats.reviews`
WHERE submitted_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
  AND reviewer_type = 'User'
GROUP BY reviewer
ORDER BY reviews_given DESC
```

### Commit Attribution

```sql
SELECT 
  c.author,
  COUNT(DISTINCT c.sha) as commits_count,
  COUNT(DISTINCT c.pr_number) as prs_contributed,
  COUNT(DISTINCT c.repository) as repos_contributed
FROM `your-project.github_stats.commits` c
WHERE c.commit_date >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 DAY)
GROUP BY c.author
ORDER BY commits_count DESC
```

## Rate Limiting

The system respects GitHub's API rate limits:

- **Default limit**: 5,000 requests per hour
- **Conservative setting**: 4,500 requests per hour (configurable)
- **Automatic throttling**: Waits when approaching limits
- **Header-based tracking**: Uses GitHub's rate limit headers for accuracy

The rate limiter will automatically wait when:
- Remaining requests drop below 100
- Local request count exceeds configured limit
- GitHub returns rate limit errors

## Deployment

### Running as a Service (systemd)

Create `/etc/systemd/system/github-collector.service`:

```ini
[Unit]
Description=GitHub Stats Collector
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/github-fetcher
Environment="GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json"
EnvironmentFile=/path/to/github-fetcher/.env
ExecStart=/path/to/venv/bin/python main.py scheduled --interval 6
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable github-collector
sudo systemctl start github-collector
sudo systemctl status github-collector
```

### Docker Deployment

Create a `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py", "scheduled", "--interval", "6"]
```

Build and run:
```bash
docker build -t github-collector .
docker run -d \
  --name github-collector \
  --env-file .env \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json \
  -v /path/to/credentials.json:/app/credentials.json:ro \
  github-collector
```

## Troubleshooting

### Rate Limit Issues

If you hit rate limits frequently:
1. Reduce `MAX_WORKERS` in `.env`
2. Increase collection intervals
3. Use more specific repository filters

### BigQuery Permissions

Ensure your service account has:
- `bigquery.datasets.create`
- `bigquery.tables.create`
- `bigquery.tables.updateData`
- `bigquery.jobs.create`

### Missing Data

The system handles missing data gracefully:
- PRs without commits are still recorded
- Reviews without comments are captured
- Bot activity is included by default

Check logs for warnings about specific data fetch failures.

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

[Add your license here]

## Support

For issues, questions, or contributions, please open an issue on GitHub.

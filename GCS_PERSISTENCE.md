# GCS Persistence Layer

The GitHub Stats Collector now includes a persistence layer using Google Cloud Storage (GCS). This feature provides:

1. **Fault Tolerance**: Resume collection if the process crashes
2. **Data Preservation**: Keep raw GitHub data for reprocessing
3. **Flexibility**: Wipe and reinsert data without re-fetching from GitHub

## Architecture

```
GitHub API → Collector → GCS Bucket → BigQuery
                  ↓
            Checkpoints
```

### Data Flow

1. **Fetch**: Data is fetched from GitHub API
2. **Persist**: Data is written to GCS in chunked JSON files
3. **Checkpoint**: Progress is checkpointed for resume capability
4. **Load**: Data is loaded from GCS and inserted into BigQuery

## Configuration

Enable GCS persistence in your `.env` file:

```bash
# GCS Configuration
GCS_BUCKET_NAME=github-stats-data        # Your GCS bucket name
GCS_CHUNK_SIZE=100                        # Items per file chunk
PERSIST_TO_GCS=true                       # Enable GCS persistence
```

## Bucket Structure

Data is organized in GCS as follows:

```
bucket/
├── askscio/                              # Organization
│   ├── repo1/                            # Repository
│   │   ├── pull_requests/                # Data type
│   │   │   └── 2025-01-01/              # Date partition
│   │   │       ├── 2025-01-01T12:00:00_chunk_0.json
│   │   │       └── 2025-01-01T12:00:00_chunk_1.json
│   │   ├── commits/
│   │   ├── reviews/
│   │   ├── review_comments/
│   │   └── issue_comments/
│   └── _checkpoints/                     # Checkpoints for resume
│       └── 2025-01-01T12:00:00+00:00.json
```

## Commands

### Collect with GCS Persistence

All collection commands automatically persist to GCS when `PERSIST_TO_GCS=true`:

```bash
# Backfill will persist to GCS first
python main.py backfill --days 180

# Incremental collect also persists
python main.py collect --hours 24
```

### Load from GCS to BigQuery

Load all data from GCS and insert into BigQuery:

```bash
python main.py load-gcs
```

Load specific repository:

```bash
python main.py load-gcs --repo frontend
```

Load data from a specific date:

```bash
python main.py load-gcs --date 2025-01-01
```

Load specific repo and date:

```bash
python main.py load-gcs --repo backend --date 2025-01-15
```

### View GCS Data Summary

See what data is stored in GCS:

```bash
python main.py gcs-summary
```

Output example:
```json
{
  "organization": "askscio",
  "repositories": {
    "frontend": {
      "pull_requests": {
        "file_count": 25,
        "size_bytes": 1048576
      },
      "commits": {
        "file_count": 30,
        "size_bytes": 524288
      }
    }
  },
  "total_files": 120,
  "total_size_bytes": 5242880
}
```

### Wipe GCS Data

Delete all GCS data for a repository:

```bash
python main.py wipe-gcs --repo my-repo --confirm
```

**Warning**: This is destructive and requires `--confirm` flag.

### Resume Failed Collection

If a collection process crashes, resume it using the collection ID:

```bash
# Get collection ID from logs or checkpoint files
python main.py resume --collection-id 2025-01-01T12:00:00+00:00
```

The resume feature:
- Reads the checkpoint to see what was completed
- Skips already processed repositories
- Continues from where it left off

## Use Cases

### Use Case 1: Wipe and Reinsert Data

If you need to reprocess data (e.g., schema changes):

```bash
# 1. Delete data from BigQuery (manually or via SQL)
DELETE FROM `project.github_stats.pull_requests` WHERE repository = 'frontend';

# 2. Reload from GCS (data is still there!)
python main.py load-gcs --repo frontend
```

### Use Case 2: Resume After Crash

```bash
# 1. Start a large backfill
python main.py backfill --days 365

# 2. Process crashes after processing 10/50 repos

# 3. Check logs for collection ID:
# "collection_id": "2025-01-01T08:30:00+00:00"

# 4. Resume
python main.py resume --collection-id 2025-01-01T08:30:00+00:00
```

### Use Case 3: Historical Data Archive

Keep a complete archive of GitHub data:

```bash
# Collect data monthly
python main.py backfill --days 30

# Data is automatically stored in GCS with date partitions
# You can always reload historical data:
python main.py load-gcs --date 2024-06-01
```

### Use Case 4: Separate Fetch and Load

Fetch data during off-peak hours, load later:

```bash
# Step 1: Fetch from GitHub (uses API rate limits)
# Set PERSIST_TO_GCS=true but don't load to BigQuery immediately
# (This requires a code modification to skip the load step)

# Step 2: Later, load to BigQuery (no GitHub API calls)
python main.py load-gcs
```

## Checkpoints

Checkpoints are automatically created when using GCS persistence:

```json
{
  "organization": "askscio",
  "collection_id": "2025-01-01T12:00:00+00:00",
  "timestamp": "2025-01-01T12:30:00+00:00",
  "data": {
    "completed_repos": ["frontend", "backend", "api"],
    "since": "2024-07-01T00:00:00+00:00",
    "until": "2025-01-01T00:00:00+00:00",
    "blob_paths": {
      "frontend": {
        "pull_requests": ["path/to/chunk_0.json", "path/to/chunk_1.json"],
        "commits": ["path/to/chunk_0.json"]
      }
    }
  }
}
```

## Performance Considerations

### Chunk Size

The `GCS_CHUNK_SIZE` parameter controls how many items are written per file:

- **Smaller chunks** (50-100): Better for incremental updates, more files
- **Larger chunks** (200-500): Fewer files, larger individual files

Recommended: **100** (default)

### Costs

GCS storage costs:
- **Standard storage**: ~$0.02/GB/month
- **Operations**: Minimal for this use case

For 1 year of data for 50 repositories:
- Estimated size: 10-50 GB
- Monthly cost: $0.20-$1.00

### Network Transfer

Data flow:
1. GitHub → Collector: GitHub API bandwidth
2. Collector → GCS: Fast (within GCP if running on GCP)
3. GCS → BigQuery: Fast (within GCP)

## Troubleshooting

### "Bucket does not exist"

The bucket is created automatically if it doesn't exist. Ensure your service account has:
- `storage.buckets.create`
- `storage.buckets.get`

### "Permission denied" on bucket operations

Service account needs:
- `storage.objects.create`
- `storage.objects.get`
- `storage.objects.delete`
- `storage.objects.list`

Grant `Storage Object Admin` role to your service account.

### Resume not working

Check that:
1. `PERSIST_TO_GCS=true` in your environment
2. Checkpoint file exists in `org/_checkpoints/` folder
3. Collection ID matches the checkpoint filename

### Large number of small files

If you have many small files:
1. Increase `GCS_CHUNK_SIZE` to consolidate data
2. Use lifecycle policies to archive old data
3. Consider periodic consolidation jobs

## Best Practices

1. **Enable GCS Persistence**: Always use `PERSIST_TO_GCS=true` for production
2. **Monitor Storage**: Use `gcs-summary` to track storage usage
3. **Lifecycle Policies**: Set up GCS lifecycle policies to archive old data
4. **Backup BigQuery**: GCS serves as your backup; don't delete unless sure
5. **Test Resume**: Periodically test the resume functionality
6. **Use Checkpoints**: Note collection IDs in logs for potential resume

## Disabling GCS Persistence

To use direct BigQuery insertion (old behavior):

```bash
PERSIST_TO_GCS=false
```

Or remove the environment variable. The system will work without GCS but:
- No resume capability
- No data preservation
- Cannot wipe and reload data

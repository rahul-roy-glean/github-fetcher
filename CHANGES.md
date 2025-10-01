# GCS Persistence Layer - Changes Summary

## What's New

The GitHub Stats Collector has been enhanced with a **GCS Persistence Layer** that provides fault tolerance, data preservation, and resume capabilities.

## Key Changes

### 1. New Storage Module (`utils/storage.py`)

A comprehensive GCS storage module that provides:
- Chunked file writing to GCS buckets
- Organized folder structure (org/repo/data-type/date)
- Checkpoint management for resume capability
- Data summary and cleanup operations
- Read/write operations with error handling

### 2. Enhanced Collector Module (`modules/collector.py`)

The collector now:
- **Persists to GCS first** before loading to BigQuery
- **Writes checkpoints** to track progress
- **Supports resume** from failed collections
- **Loads from GCS** to BigQuery independently
- Maintains backward compatibility (can disable GCS persistence)

### 3. New Configuration Options

Added to `config.py` and `.env`:
```bash
GCS_BUCKET_NAME=github-stats-data      # Bucket name
GCS_CHUNK_SIZE=100                      # Items per file
PERSIST_TO_GCS=true                     # Enable/disable GCS
```

### 4. New CLI Commands

Added five new commands to `main.py`:

#### `load-gcs`
Load data from GCS to BigQuery:
```bash
python main.py load-gcs
python main.py load-gcs --repo frontend
python main.py load-gcs --date 2025-01-01
```

#### `gcs-summary`
View what's stored in GCS:
```bash
python main.py gcs-summary
```

#### `wipe-gcs`
Delete GCS data for a repository:
```bash
python main.py wipe-gcs --repo my-repo --confirm
```

#### `resume`
Resume a failed collection:
```bash
python main.py resume --collection-id 2025-01-01T12:00:00+00:00
```

### 5. Updated Dependencies

Added to `requirements.txt`:
```
google-cloud-storage>=2.10.0
```

### 6. New Documentation

- **GCS_PERSISTENCE.md**: Complete guide to GCS persistence layer
- **Updated README.md**: Added GCS features and usage
- **Updated QUICKSTART.md**: Added GCS quick start section
- **CHANGES.md**: This document

## Data Flow Comparison

### Before (Direct to BigQuery)
```
GitHub API → Collector → BigQuery
```

**Issues**:
- If process crashes, must restart from scratch
- Cannot reprocess data without re-fetching from GitHub
- No audit trail of raw data

### After (With GCS Persistence)
```
GitHub API → Collector → GCS Bucket → BigQuery
                  ↓
            Checkpoints
```

**Benefits**:
- Process can be resumed from checkpoints
- Raw data preserved in GCS for reprocessing
- Can wipe and reload BigQuery without GitHub API calls
- Audit trail of all collected data

## Bucket Structure

Data is organized in GCS as:
```
bucket/
├── askscio/                              # Organization
│   ├── repo1/                            # Repository
│   │   ├── pull_requests/                # Data type
│   │   │   └── 2025-01-01/              # Date partition
│   │   │       ├── timestamp_chunk_0.json
│   │   │       └── timestamp_chunk_1.json
│   │   ├── commits/
│   │   ├── reviews/
│   │   ├── review_comments/
│   │   └── issue_comments/
│   └── _checkpoints/                     # Resume checkpoints
│       └── collection-id.json
```

## Use Cases Enabled

### 1. Fault Tolerance
If a backfill crashes after processing 10/50 repositories:
```bash
python main.py resume --collection-id 2025-01-01T12:00:00+00:00
```
Only processes the remaining 40 repositories.

### 2. Data Reprocessing
If you update BigQuery schema:
```sql
-- Update schema in BigQuery
ALTER TABLE ...

-- Delete old data
DELETE FROM `project.dataset.pull_requests` WHERE repository = 'frontend';

-- Reload from GCS (no GitHub API calls!)
python main.py load-gcs --repo frontend
```

### 3. Historical Archive
All data is automatically preserved in GCS:
```bash
# View what's archived
python main.py gcs-summary

# Reload historical data
python main.py load-gcs --date 2024-06-01
```

### 4. Debugging and Validation
Inspect raw GitHub data in GCS:
```bash
gsutil cat gs://bucket/askscio/repo/pull_requests/2025-01-01/timestamp_chunk_0.json
```

## Backward Compatibility

The system maintains full backward compatibility:

### Disable GCS Persistence
```bash
PERSIST_TO_GCS=false
```

The collector will work exactly as before (direct to BigQuery).

### Gradual Migration
Can enable GCS for new collections while keeping old data:
1. Run new collections with `PERSIST_TO_GCS=true`
2. Old data remains in BigQuery
3. New data goes through GCS layer

## Performance Impact

### Storage Overhead
- Minimal: ~10-50 GB for 1 year of data for 50 repos
- Cost: ~$0.20-$1.00/month

### Processing Time
- Slightly slower (~10-20%) due to GCS write/read
- Offset by resume capability (saves time on failures)
- No additional GitHub API calls

### Network
- All within GCP (fast and free between services)
- No egress charges

## Migration Guide

### For New Installations
1. Use the updated `.env.example`
2. Set `GCS_BUCKET_NAME` and `PERSIST_TO_GCS=true`
3. Run normally - bucket created automatically

### For Existing Installations
1. Update code: `git pull`
2. Install new dependency: `pip install google-cloud-storage>=2.10.0`
3. Update `.env`:
   ```bash
   GCS_BUCKET_NAME=github-stats-data
   PERSIST_TO_GCS=true
   ```
4. Ensure service account has Storage Object Admin role
5. Next collection will use GCS automatically

### Testing the New Features
```bash
# 1. Small test collection
python main.py collect --hours 1

# 2. Check GCS
python main.py gcs-summary

# 3. Test load from GCS
python main.py load-gcs --date $(date +%Y-%m-%d)

# 4. Test resume (simulate crash by Ctrl+C during collection)
python main.py backfill --days 7
# Press Ctrl+C after a few repos complete
# Note the collection ID from logs
python main.py resume --collection-id <collection-id>
```

## Breaking Changes

None! The system is fully backward compatible.

## Configuration Changes

### New Environment Variables
- `GCS_BUCKET_NAME`: Required if using GCS persistence
- `GCS_CHUNK_SIZE`: Optional, defaults to 100
- `PERSIST_TO_GCS`: Optional, defaults to true

### Modified Behavior
When `PERSIST_TO_GCS=true`:
- Collections persist to GCS first
- Data then loaded from GCS to BigQuery
- Checkpoints created automatically
- Collection ID logged for resume capability

## Service Account Permissions

Add these GCS permissions to your service account:
- `storage.buckets.create`
- `storage.objects.create`
- `storage.objects.get`
- `storage.objects.delete`
- `storage.objects.list`

Or use the predefined role:
- `Storage Object Admin`

## Monitoring

### Check Collection Progress
```bash
# View logs
tail -f github_collector.log

# Check GCS data
python main.py gcs-summary

# Inspect specific data
gsutil ls -lh gs://your-bucket/askscio/
```

### Validate Data
```bash
# Count records in GCS vs BigQuery
python main.py gcs-summary  # Shows file counts

# Query BigQuery
bq query --use_legacy_sql=false '
  SELECT 
    repository,
    COUNT(*) as pr_count 
  FROM `project.dataset.pull_requests` 
  GROUP BY repository
'
```

## Troubleshooting

### "Bucket not found"
Bucket is created automatically. Check service account permissions.

### "Permission denied"
Grant `Storage Object Admin` role to service account.

### Resume not finding checkpoint
- Ensure collection ID is exact (copy from logs)
- Check checkpoint exists: `gsutil ls gs://bucket/org/_checkpoints/`
- Verify `PERSIST_TO_GCS=true`

### High storage costs
- Adjust `GCS_CHUNK_SIZE` to use larger chunks
- Set up GCS lifecycle policies to archive old data
- Consider Nearline/Coldline storage for old data

## Future Enhancements

Potential future improvements:
1. Incremental checkpoint updates (checkpoint each repo)
2. Parallel GCS-to-BigQuery loading
3. Data compression in GCS
4. S3 support as alternative to GCS
5. Automatic consolidation of small files

## Questions?

See detailed documentation:
- `GCS_PERSISTENCE.md` - Full GCS persistence guide
- `README.md` - Complete system documentation
- `QUICKSTART.md` - Quick start guide

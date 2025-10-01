"""
Configuration for GitHub Stats Collector
"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    """Main configuration class"""
    
    # GitHub Configuration
    github_token: str
    github_org: str = "askscio"
    
    # BigQuery Configuration
    bigquery_project_id: str
    bigquery_dataset_id: str = "github_stats"
    bigquery_location: str = "US"
    
    # GCS Configuration
    gcs_bucket_name: str = "github-stats-data"
    gcs_chunk_size: int = 100  # Number of items per file chunk
    
    # Rate Limiting Configuration
    max_requests_per_hour: int = 4500  # Conservative limit (5000 is GitHub's limit)
    rate_limit_buffer: float = 0.9  # Use 90% of available requests
    
    # Parallelism Configuration
    max_workers: int = 10  # Number of parallel workers for fetching
    batch_size: int = 100  # Number of items to process in a batch
    
    # Collection Configuration
    default_lookback_days: int = 180  # 6 months default for backfill
    collection_cadence_hours: int = 6  # How often to run collection job
    persist_to_gcs: bool = True  # Whether to persist to GCS before BigQuery
    
    @classmethod
    def from_env(cls) -> "Config":
        """Create config from environment variables"""
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            raise ValueError("GITHUB_TOKEN environment variable is required")
        
        bigquery_project_id = os.getenv("BIGQUERY_PROJECT_ID")
        if not bigquery_project_id:
            raise ValueError("BIGQUERY_PROJECT_ID environment variable is required")
        
        gcs_bucket_name = os.getenv("GCS_BUCKET_NAME", "github-stats-data")
        
        return cls(
            github_token=github_token,
            github_org=os.getenv("GITHUB_ORG", "askscio"),
            bigquery_project_id=bigquery_project_id,
            bigquery_dataset_id=os.getenv("BIGQUERY_DATASET_ID", "github_stats"),
            bigquery_location=os.getenv("BIGQUERY_LOCATION", "US"),
            gcs_bucket_name=gcs_bucket_name,
            gcs_chunk_size=int(os.getenv("GCS_CHUNK_SIZE", "100")),
            max_workers=int(os.getenv("MAX_WORKERS", "10")),
            batch_size=int(os.getenv("BATCH_SIZE", "100")),
            default_lookback_days=int(os.getenv("DEFAULT_LOOKBACK_DAYS", "180")),
            persist_to_gcs=os.getenv("PERSIST_TO_GCS", "true").lower() == "true",
        )


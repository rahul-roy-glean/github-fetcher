"""
BigQuery Schema Module
Creates and manages BigQuery datasets and tables for GitHub stats
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from google.cloud import bigquery
from google.cloud.exceptions import NotFound, Conflict

logger = logging.getLogger(__name__)


class BigQuerySchema:
    """Manages BigQuery schema creation and updates"""
    
    def __init__(self, project_id: str, dataset_id: str, location: str = "US"):
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.location = location
        self.client = bigquery.Client(project=project_id)
    
    def create_dataset(self, exists_ok: bool = True) -> bigquery.Dataset:
        """Create the dataset if it doesn't exist"""
        dataset_ref = f"{self.project_id}.{self.dataset_id}"
        
        try:
            dataset = self.client.get_dataset(dataset_ref)
            logger.info(f"Dataset {dataset_ref} already exists")
            return dataset
        except NotFound:
            logger.info(f"Creating dataset {dataset_ref}")
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = self.location
            dataset.description = "GitHub statistics and metrics"
            return self.client.create_dataset(dataset, exists_ok=exists_ok)
    
    def _get_pull_requests_schema(self) -> List[bigquery.SchemaField]:
        """Define schema for pull requests table"""
        return [
            bigquery.SchemaField("pr_number", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("repository", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("organization", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("title", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("state", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("author", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("author_type", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("closed_at", "TIMESTAMP", mode="NULLABLE"),
            bigquery.SchemaField("merged_at", "TIMESTAMP", mode="NULLABLE"),
            bigquery.SchemaField("url", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("additions", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("deletions", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("changed_files", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("labels", "STRING", mode="REPEATED"),
            bigquery.SchemaField("size_label", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("commit_count", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("review_count", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("review_comment_count", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("issue_comment_count", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("is_draft", "BOOLEAN", mode="REQUIRED"),
            bigquery.SchemaField("is_merged", "BOOLEAN", mode="REQUIRED"),
            bigquery.SchemaField("merge_commit_sha", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("base_ref", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("head_ref", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("ingestion_timestamp", "TIMESTAMP", mode="REQUIRED"),
        ]
    
    def _get_commits_schema(self) -> List[bigquery.SchemaField]:
        """Define schema for commits table"""
        return [
            bigquery.SchemaField("sha", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("pr_number", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("repository", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("organization", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("author", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("author_email", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("committer", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("committer_email", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("message", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("commit_date", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("author_date", "TIMESTAMP", mode="NULLABLE"),
            bigquery.SchemaField("url", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("ingestion_timestamp", "TIMESTAMP", mode="REQUIRED"),
        ]
    
    def _get_reviews_schema(self) -> List[bigquery.SchemaField]:
        """Define schema for reviews table"""
        return [
            bigquery.SchemaField("review_id", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("pr_number", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("repository", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("organization", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("reviewer", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("reviewer_type", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("state", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("body", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("submitted_at", "TIMESTAMP", mode="NULLABLE"),
            bigquery.SchemaField("commit_id", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("url", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("ingestion_timestamp", "TIMESTAMP", mode="REQUIRED"),
        ]
    
    def _get_review_comments_schema(self) -> List[bigquery.SchemaField]:
        """Define schema for review comments table"""
        return [
            bigquery.SchemaField("comment_id", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("pr_number", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("repository", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("organization", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("author", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("author_type", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("body", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("path", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("position", "INTEGER", mode="NULLABLE"),
            bigquery.SchemaField("commit_id", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("url", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("ingestion_timestamp", "TIMESTAMP", mode="REQUIRED"),
        ]
    
    def _get_issue_comments_schema(self) -> List[bigquery.SchemaField]:
        """Define schema for issue/PR comments table"""
        return [
            bigquery.SchemaField("comment_id", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("pr_number", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("repository", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("organization", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("author", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("author_type", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("body", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("url", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("ingestion_timestamp", "TIMESTAMP", mode="REQUIRED"),
        ]
    
    def _get_metrics_schema(self) -> List[bigquery.SchemaField]:
        """Define schema for derived metrics table"""
        return [
            bigquery.SchemaField("metric_date", "DATE", mode="REQUIRED"),
            bigquery.SchemaField("repository", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("organization", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("author", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("author_type", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("prs_opened", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("prs_merged", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("prs_closed", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("commits_count", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("reviews_given", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("review_comments_given", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("lines_added", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("lines_deleted", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("files_changed", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("calculation_timestamp", "TIMESTAMP", mode="REQUIRED"),
        ]
    
    def create_table(self, table_id: str, schema: List[bigquery.SchemaField],
                    partition_field: Optional[str] = None,
                    clustering_fields: Optional[List[str]] = None,
                    exists_ok: bool = True) -> bigquery.Table:
        """Create a table with the specified schema"""
        table_ref = f"{self.project_id}.{self.dataset_id}.{table_id}"
        
        try:
            table = self.client.get_table(table_ref)
            logger.info(f"Table {table_ref} already exists")
            return table
        except NotFound:
            logger.info(f"Creating table {table_ref}")
            table = bigquery.Table(table_ref, schema=schema)
            
            # Add partitioning if specified
            if partition_field:
                table.time_partitioning = bigquery.TimePartitioning(
                    type_=bigquery.TimePartitioningType.DAY,
                    field=partition_field,
                )
            
            # Add clustering if specified
            if clustering_fields:
                table.clustering_fields = clustering_fields
            
            return self.client.create_table(table, exists_ok=exists_ok)
    
    def create_all_tables(self) -> Dict[str, bigquery.Table]:
        """Create all required tables"""
        logger.info("Creating all BigQuery tables")
        
        # Ensure dataset exists
        self.create_dataset()
        
        tables = {}
        
        # Pull Requests table
        tables['pull_requests'] = self.create_table(
            "pull_requests",
            self._get_pull_requests_schema(),
            partition_field="updated_at",
            clustering_fields=["organization", "repository", "author"]
        )
        
        # Commits table
        tables['commits'] = self.create_table(
            "commits",
            self._get_commits_schema(),
            partition_field="commit_date",
            clustering_fields=["organization", "repository", "author"]
        )
        
        # Reviews table
        tables['reviews'] = self.create_table(
            "reviews",
            self._get_reviews_schema(),
            partition_field="submitted_at",
            clustering_fields=["organization", "repository", "reviewer"]
        )
        
        # Review Comments table
        tables['review_comments'] = self.create_table(
            "review_comments",
            self._get_review_comments_schema(),
            partition_field="created_at",
            clustering_fields=["organization", "repository", "author"]
        )
        
        # Issue Comments table
        tables['issue_comments'] = self.create_table(
            "issue_comments",
            self._get_issue_comments_schema(),
            partition_field="created_at",
            clustering_fields=["organization", "repository", "author"]
        )
        
        # Metrics table
        tables['metrics'] = self.create_table(
            "metrics",
            self._get_metrics_schema(),
            partition_field="metric_date",
            clustering_fields=["organization", "repository", "author"]
        )
        
        logger.info(f"Created {len(tables)} tables")
        return tables
    
    def get_table_reference(self, table_id: str) -> str:
        """Get full table reference"""
        return f"{self.project_id}.{self.dataset_id}.{table_id}"


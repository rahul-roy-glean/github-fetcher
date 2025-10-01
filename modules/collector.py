"""
Collector Job Module
Ongoing collection job that curates GitHub data and publishes to BigQuery
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from google.cloud import bigquery
from google.cloud.exceptions import NotFound

from config import Config
from utils.github_client import GitHubClient
from utils.storage import GCSStorage
from modules.fetcher import GitHubFetcher, PullRequestData
from modules.schema import BigQuerySchema

logger = logging.getLogger(__name__)


class GitHubCollector:
    """Collects GitHub data and publishes to BigQuery (optionally via GCS)"""
    
    def __init__(self, config: Config):
        self.config = config
        self.github_client = GitHubClient(
            config.github_token,
            config.max_requests_per_hour
        )
        self.fetcher = GitHubFetcher(self.github_client, config.max_workers)
        self.bq_schema = BigQuerySchema(
            config.bigquery_project_id,
            config.bigquery_dataset_id,
            config.bigquery_location
        )
        self.bq_client = bigquery.Client(project=config.bigquery_project_id)
        
        # Initialize GCS storage if persistence is enabled
        if config.persist_to_gcs:
            self.storage = GCSStorage(
                config.gcs_bucket_name,
                config.bigquery_project_id
            )
        else:
            self.storage = None
    
    def initialize_bigquery(self):
        """Initialize BigQuery dataset and tables"""
        logger.info("Initializing BigQuery schema")
        tables = self.bq_schema.create_all_tables()
        logger.info(f"BigQuery initialization complete: {len(tables)} tables ready")
    
    def _prepare_pr_rows(self, pr_data_list: List[PullRequestData]) -> List[Dict[str, Any]]:
        """Prepare PR data for BigQuery insertion"""
        rows = []
        ingestion_timestamp = datetime.now(timezone.utc)
        
        for pr in pr_data_list:
            row = {
                "pr_number": pr.pr_number,
                "repository": pr.repository,
                "organization": pr.organization,
                "title": pr.title,
                "state": pr.state,
                "author": pr.author,
                "author_type": pr.author_type,
                "created_at": pr.created_at.isoformat(),
                "updated_at": pr.updated_at.isoformat(),
                "closed_at": pr.closed_at.isoformat() if pr.closed_at else None,
                "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
                "url": pr.url,
                "additions": pr.additions,
                "deletions": pr.deletions,
                "changed_files": pr.changed_files,
                "labels": pr.labels,
                "size_label": pr.size_label,
                "commit_count": pr.commit_count,
                "review_count": pr.review_count,
                "review_comment_count": pr.review_comment_count,
                "issue_comment_count": pr.issue_comment_count,
                "is_draft": pr.is_draft,
                "is_merged": pr.is_merged,
                "merge_commit_sha": pr.merge_commit_sha,
                "base_ref": pr.base_ref,
                "head_ref": pr.head_ref,
                "ingestion_timestamp": ingestion_timestamp.isoformat(),
            }
            rows.append(row)
        
        return rows
    
    def _prepare_commit_rows(self, pr_data_list: List[PullRequestData]) -> List[Dict[str, Any]]:
        """Prepare commit data for BigQuery insertion"""
        rows = []
        ingestion_timestamp = datetime.now(timezone.utc)
        
        for pr in pr_data_list:
            for commit in pr.commits:
                commit_info = commit.get('commit', {})
                author_info = commit_info.get('author', {})
                committer_info = commit_info.get('committer', {})
                
                # Parse commit date
                commit_date = commit_info.get('committer', {}).get('date')
                if commit_date:
                    commit_date = datetime.fromisoformat(commit_date.replace('Z', '+00:00')).isoformat()
                
                author_date = author_info.get('date')
                if author_date:
                    author_date = datetime.fromisoformat(author_date.replace('Z', '+00:00')).isoformat()
                
                row = {
                    "sha": commit.get('sha', ''),
                    "pr_number": pr.pr_number,
                    "repository": pr.repository,
                    "organization": pr.organization,
                    "author": author_info.get('name'),
                    "author_email": author_info.get('email'),
                    "committer": committer_info.get('name'),
                    "committer_email": committer_info.get('email'),
                    "message": commit_info.get('message', ''),
                    "commit_date": commit_date,
                    "author_date": author_date,
                    "url": commit.get('html_url', ''),
                    "ingestion_timestamp": ingestion_timestamp.isoformat(),
                }
                rows.append(row)
        
        return rows
    
    def _prepare_review_rows(self, pr_data_list: List[PullRequestData]) -> List[Dict[str, Any]]:
        """Prepare review data for BigQuery insertion"""
        rows = []
        ingestion_timestamp = datetime.now(timezone.utc)
        
        for pr in pr_data_list:
            for review in pr.reviews:
                user = review.get('user', {})
                submitted_at = review.get('submitted_at')
                if submitted_at:
                    submitted_at = datetime.fromisoformat(submitted_at.replace('Z', '+00:00')).isoformat()
                
                row = {
                    "review_id": review.get('id', 0),
                    "pr_number": pr.pr_number,
                    "repository": pr.repository,
                    "organization": pr.organization,
                    "reviewer": user.get('login', 'unknown'),
                    "reviewer_type": user.get('type', 'User'),
                    "state": review.get('state', 'unknown'),
                    "body": review.get('body'),
                    "submitted_at": submitted_at,
                    "commit_id": review.get('commit_id'),
                    "url": review.get('html_url', ''),
                    "ingestion_timestamp": ingestion_timestamp.isoformat(),
                }
                rows.append(row)
        
        return rows
    
    def _prepare_review_comment_rows(self, pr_data_list: List[PullRequestData]) -> List[Dict[str, Any]]:
        """Prepare review comment data for BigQuery insertion"""
        rows = []
        ingestion_timestamp = datetime.now(timezone.utc)
        
        for pr in pr_data_list:
            for comment in pr.review_comments:
                user = comment.get('user', {})
                created_at = datetime.fromisoformat(comment['created_at'].replace('Z', '+00:00')).isoformat()
                updated_at = datetime.fromisoformat(comment['updated_at'].replace('Z', '+00:00')).isoformat()
                
                row = {
                    "comment_id": comment.get('id', 0),
                    "pr_number": pr.pr_number,
                    "repository": pr.repository,
                    "organization": pr.organization,
                    "author": user.get('login', 'unknown'),
                    "author_type": user.get('type', 'User'),
                    "body": comment.get('body'),
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "path": comment.get('path'),
                    "position": comment.get('position'),
                    "commit_id": comment.get('commit_id'),
                    "url": comment.get('html_url', ''),
                    "ingestion_timestamp": ingestion_timestamp.isoformat(),
                }
                rows.append(row)
        
        return rows
    
    def _prepare_issue_comment_rows(self, pr_data_list: List[PullRequestData]) -> List[Dict[str, Any]]:
        """Prepare issue comment data for BigQuery insertion"""
        rows = []
        ingestion_timestamp = datetime.now(timezone.utc)
        
        for pr in pr_data_list:
            for comment in pr.issue_comments:
                user = comment.get('user', {})
                created_at = datetime.fromisoformat(comment['created_at'].replace('Z', '+00:00')).isoformat()
                updated_at = datetime.fromisoformat(comment['updated_at'].replace('Z', '+00:00')).isoformat()
                
                row = {
                    "comment_id": comment.get('id', 0),
                    "pr_number": pr.pr_number,
                    "repository": pr.repository,
                    "organization": pr.organization,
                    "author": user.get('login', 'unknown'),
                    "author_type": user.get('type', 'User'),
                    "body": comment.get('body'),
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "url": comment.get('html_url', ''),
                    "ingestion_timestamp": ingestion_timestamp.isoformat(),
                }
                rows.append(row)
        
        return rows
    
    def _get_merge_key(self, table_id: str) -> List[str]:
        """Get the unique key fields for a table"""
        merge_keys = {
            "pull_requests": ["pr_number", "repository", "organization"],
            "commits": ["sha", "repository", "organization"],
            "reviews": ["review_id", "repository", "organization"],
            "review_comments": ["comment_id", "repository", "organization"],
            "issue_comments": ["comment_id", "repository", "organization"],
        }
        return merge_keys.get(table_id, [])
    
    def _upsert_rows(self, table_id: str, rows: List[Dict[str, Any]]) -> int:
        """Upsert rows into BigQuery table using MERGE to avoid duplicates"""
        if not rows:
            logger.info(f"No rows to upsert into {table_id}")
            return 0
        
        table_ref = self.bq_schema.get_table_reference(table_id)
        logger.info(f"Upserting {len(rows)} rows into {table_ref}")
        
        # Get merge keys for this table
        merge_keys = self._get_merge_key(table_id)
        if not merge_keys:
            logger.warning(f"No merge keys defined for {table_id}, using insert")
            return self._insert_rows(table_id, rows)
        
        # Create a temporary table with the new data
        temp_table_id = f"{table_id}_temp_{int(datetime.now(timezone.utc).timestamp())}"
        temp_table_ref = f"{self.config.bigquery_project_id}.{self.config.bigquery_dataset_id}.{temp_table_id}"
        
        try:
            # Create temporary table with same schema
            source_table = self.bq_client.get_table(table_ref)
            temp_table = bigquery.Table(temp_table_ref, schema=source_table.schema)
            temp_table = self.bq_client.create_table(temp_table)
            
            # Insert data into temporary table
            errors = self.bq_client.insert_rows_json(temp_table_ref, rows)
            if errors:
                logger.error(f"Errors inserting into temp table: {errors}")
                self.bq_client.delete_table(temp_table_ref)
                return 0
            
            # Build MERGE query
            merge_condition = " AND ".join([f"target.{key} = source.{key}" for key in merge_keys])
            
            # Get all column names from schema
            columns = [field.name for field in source_table.schema]
            update_set = ", ".join([f"{col} = source.{col}" for col in columns if col not in merge_keys])
            insert_cols = ", ".join(columns)
            insert_vals = ", ".join([f"source.{col}" for col in columns])
            
            merge_query = f"""
            MERGE `{table_ref}` AS target
            USING `{temp_table_ref}` AS source
            ON {merge_condition}
            WHEN MATCHED THEN
                UPDATE SET {update_set}
            WHEN NOT MATCHED THEN
                INSERT ({insert_cols})
                VALUES ({insert_vals})
            """
            
            # Execute MERGE
            query_job = self.bq_client.query(merge_query)
            query_job.result()  # Wait for completion
            
            # Get number of rows affected
            rows_affected = query_job.num_dml_affected_rows or len(rows)
            
            # Clean up temporary table
            self.bq_client.delete_table(temp_table_ref)
            
            logger.info(f"Successfully upserted {rows_affected} rows into {table_id}")
            return rows_affected
            
        except Exception as e:
            logger.error(f"Error during upsert: {e}")
            # Try to clean up temp table
            try:
                self.bq_client.delete_table(temp_table_ref)
            except:
                pass
            return 0
    
    def _insert_rows(self, table_id: str, rows: List[Dict[str, Any]]) -> int:
        """Insert rows into BigQuery table (direct insert, may create duplicates)"""
        if not rows:
            logger.info(f"No rows to insert into {table_id}")
            return 0
        
        table_ref = self.bq_schema.get_table_reference(table_id)
        logger.info(f"Inserting {len(rows)} rows into {table_ref}")
        
        errors = self.bq_client.insert_rows_json(table_ref, rows)
        
        if errors:
            logger.error(f"Errors inserting into {table_id}: {errors}")
            return 0
        
        logger.info(f"Successfully inserted {len(rows)} rows into {table_id}")
        return len(rows)
    
    def persist_to_gcs(self, pr_data: Dict[str, List[PullRequestData]], 
                      collection_id: Optional[str] = None) -> Dict[str, List[str]]:
        """
        Persist collected data to GCS
        
        Args:
            pr_data: Dictionary mapping repository names to lists of PullRequestData
            collection_id: Optional collection identifier for tracking
        
        Returns:
            Dictionary with lists of blob paths per repository
        """
        if not self.storage:
            raise ValueError("GCS storage not configured. Set persist_to_gcs=True")
        
        logger.info("Persisting data to GCS")
        
        if collection_id is None:
            collection_id = datetime.now(timezone.utc).isoformat()
        
        blob_paths = {}
        timestamp = collection_id
        
        for repo, pr_list in pr_data.items():
            if not pr_list:
                continue
            
            logger.info(f"Persisting {len(pr_list)} PRs for {repo}")
            
            # Convert PR data to dictionaries
            pr_dicts = [pr.to_dict() for pr in pr_list]
            
            # Write PR data
            pr_paths = self.storage.write_data_chunks(
                self.config.github_org,
                repo,
                "pull_requests",
                pr_dicts,
                chunk_size=self.config.gcs_chunk_size,
                timestamp=timestamp
            )
            
            # Prepare and write commits
            commit_rows = self._prepare_commit_rows(pr_list)
            commit_paths = self.storage.write_data_chunks(
                self.config.github_org,
                repo,
                "commits",
                commit_rows,
                chunk_size=self.config.gcs_chunk_size,
                timestamp=timestamp
            )
            
            # Prepare and write reviews
            review_rows = self._prepare_review_rows(pr_list)
            review_paths = self.storage.write_data_chunks(
                self.config.github_org,
                repo,
                "reviews",
                review_rows,
                chunk_size=self.config.gcs_chunk_size,
                timestamp=timestamp
            )
            
            # Prepare and write review comments
            review_comment_rows = self._prepare_review_comment_rows(pr_list)
            review_comment_paths = self.storage.write_data_chunks(
                self.config.github_org,
                repo,
                "review_comments",
                review_comment_rows,
                chunk_size=self.config.gcs_chunk_size,
                timestamp=timestamp
            )
            
            # Prepare and write issue comments
            issue_comment_rows = self._prepare_issue_comment_rows(pr_list)
            issue_comment_paths = self.storage.write_data_chunks(
                self.config.github_org,
                repo,
                "issue_comments",
                issue_comment_rows,
                chunk_size=self.config.gcs_chunk_size,
                timestamp=timestamp
            )
            
            blob_paths[repo] = {
                "pull_requests": pr_paths,
                "commits": commit_paths,
                "reviews": review_paths,
                "review_comments": review_comment_paths,
                "issue_comments": issue_comment_paths
            }
        
        logger.info(f"Data persisted to GCS for {len(blob_paths)} repositories")
        return blob_paths
    
    def publish_to_bigquery(self, pr_data: Dict[str, List[PullRequestData]]) -> Dict[str, int]:
        """
        Publish collected data to BigQuery
        
        Returns:
            Dictionary with counts of inserted rows per table
        """
        logger.info("Publishing data to BigQuery")
        
        # Flatten all PR data
        all_prs = []
        for repo_prs in pr_data.values():
            all_prs.extend(repo_prs)
        
        if not all_prs:
            logger.warning("No PR data to publish")
            return {}
        
        counts = {}
        
        # Upsert PRs (avoid duplicates)
        pr_rows = self._prepare_pr_rows(all_prs)
        counts['pull_requests'] = self._upsert_rows('pull_requests', pr_rows)
        
        # Upsert commits (avoid duplicates)
        commit_rows = self._prepare_commit_rows(all_prs)
        counts['commits'] = self._upsert_rows('commits', commit_rows)
        
        # Upsert reviews (avoid duplicates)
        review_rows = self._prepare_review_rows(all_prs)
        counts['reviews'] = self._upsert_rows('reviews', review_rows)
        
        # Upsert review comments (avoid duplicates)
        review_comment_rows = self._prepare_review_comment_rows(all_prs)
        counts['review_comments'] = self._upsert_rows('review_comments', review_comment_rows)
        
        # Upsert issue comments (avoid duplicates)
        issue_comment_rows = self._prepare_issue_comment_rows(all_prs)
        counts['issue_comments'] = self._upsert_rows('issue_comments', issue_comment_rows)
        
        logger.info(f"Publishing complete: {counts}")
        return counts
    
    def load_from_gcs_and_publish(self, repo: Optional[str] = None,
                                  date_filter: Optional[str] = None) -> Dict[str, int]:
        """
        Load data from GCS and publish to BigQuery
        
        Args:
            repo: Optional repository name to load (if None, load all)
            date_filter: Optional date filter (YYYY-MM-DD)
        
        Returns:
            Dictionary with counts of inserted rows per table
        """
        if not self.storage:
            raise ValueError("GCS storage not configured")
        
        logger.info(f"Loading data from GCS for org: {self.config.github_org}")
        
        # Determine which repositories to process
        if repo:
            repos_to_process = [repo]
        else:
            repos_to_process = self.storage.list_repositories(self.config.github_org)
        
        logger.info(f"Processing {len(repos_to_process)} repositories")
        
        counts = {}
        data_types = ["pull_requests", "commits", "reviews", "review_comments", "issue_comments"]
        
        for data_type in data_types:
            all_rows = []
            
            for repo_name in repos_to_process:
                # List all data files for this repo and data type
                blob_paths = self.storage.list_data_files(
                    self.config.github_org,
                    repo_name,
                    data_type,
                    date_filter
                )
                
                logger.info(f"Found {len(blob_paths)} {data_type} files for {repo_name}")
                
                # Read and accumulate data
                for blob_path in blob_paths:
                    blob_data = self.storage.read_blob(blob_path)
                    if blob_data and 'data' in blob_data:
                        all_rows.extend(blob_data['data'])
            
            # Upsert into BigQuery (avoid duplicates)
            if all_rows:
                count = self._upsert_rows(data_type, all_rows)
                counts[data_type] = count
            else:
                counts[data_type] = 0
        
        logger.info(f"Loaded and published data from GCS: {counts}")
        return counts
    
    def collect_and_publish(self,
                           since: Optional[datetime] = None,
                           until: Optional[datetime] = None,
                           repo_filter: Optional[List[str]] = None,
                           collection_id: Optional[str] = None,
                           resume: bool = False) -> Dict[str, int]:
        """
        Collect data from GitHub and publish to BigQuery (optionally via GCS)
        
        Args:
            since: Only collect data updated after this date
            until: Only collect data updated before this date
            repo_filter: Optional list of repository names to collect
            collection_id: Optional collection identifier for tracking
            resume: Whether to resume from a checkpoint
        
        Returns:
            Dictionary with counts of inserted rows per table
        """
        logger.info(f"Starting collection for organization: {self.config.github_org}")
        logger.info(f"Date range: {since} to {until}")
        
        if collection_id is None:
            collection_id = datetime.now(timezone.utc).isoformat()
        
        # Check for resume
        completed_repos = set()
        if resume and self.storage:
            checkpoint = self.storage.read_checkpoint(self.config.github_org, collection_id)
            if checkpoint:
                completed_repos = set(checkpoint.get('data', {}).get('completed_repos', []))
                logger.info(f"Resuming collection. Already completed: {len(completed_repos)} repos")
        
        # Fetch data from GitHub
        pr_data = self.fetcher.fetch_organization_prs(
            self.config.github_org,
            since=since,
            until=until,
            parallel=True,
            repo_filter=repo_filter
        )
        
        # Filter out already completed repos if resuming
        if completed_repos:
            pr_data = {repo: prs for repo, prs in pr_data.items() if repo not in completed_repos}
            logger.info(f"After filtering completed repos: {len(pr_data)} repos remaining")
        
        # Persist to GCS if enabled
        if self.config.persist_to_gcs and self.storage:
            logger.info("Persisting data to GCS first")
            blob_paths = self.persist_to_gcs(pr_data, collection_id)
            
            # Write checkpoint after persisting
            checkpoint_data = {
                "completed_repos": list(pr_data.keys()),
                "collection_id": collection_id,
                "since": since.isoformat() if since else None,
                "until": until.isoformat() if until else None,
                "blob_paths": blob_paths
            }
            self.storage.write_checkpoint(self.config.github_org, collection_id, checkpoint_data)
            
            # Now load from GCS and publish to BigQuery
            logger.info("Loading from GCS and publishing to BigQuery")
            counts = self.load_from_gcs_and_publish()
        else:
            # Direct publish to BigQuery (old behavior)
            counts = self.publish_to_bigquery(pr_data)
        
        return counts
    
    def backfill(self, days: int = 180, repo_filter: Optional[List[str]] = None) -> Dict[str, int]:
        """
        Backfill historical data
        
        Args:
            days: Number of days to backfill
            repo_filter: Optional list of repository names to backfill
        
        Returns:
            Dictionary with counts of inserted rows per table
        """
        logger.info(f"Starting backfill for {days} days")
        
        until = datetime.now(timezone.utc)
        since = until - timedelta(days=days)
        
        return self.collect_and_publish(since=since, until=until, repo_filter=repo_filter)
    
    def incremental_collect(self, hours: int = 6, repo_filter: Optional[List[str]] = None) -> Dict[str, int]:
        """
        Collect data from the last N hours
        
        Args:
            hours: Number of hours to look back
            repo_filter: Optional list of repository names to collect
        
        Returns:
            Dictionary with counts of inserted rows per table
        """
        logger.info(f"Starting incremental collection for last {hours} hours")
        
        until = datetime.now(timezone.utc)
        since = until - timedelta(hours=hours)
        
        return self.collect_and_publish(since=since, until=until, repo_filter=repo_filter)


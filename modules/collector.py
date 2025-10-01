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
from modules.fetcher import GitHubFetcher, PullRequestData
from modules.schema import BigQuerySchema

logger = logging.getLogger(__name__)


class GitHubCollector:
    """Collects GitHub data and publishes to BigQuery"""
    
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
    
    def _insert_rows(self, table_id: str, rows: List[Dict[str, Any]]) -> int:
        """Insert rows into BigQuery table"""
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
        
        # Insert PRs
        pr_rows = self._prepare_pr_rows(all_prs)
        counts['pull_requests'] = self._insert_rows('pull_requests', pr_rows)
        
        # Insert commits
        commit_rows = self._prepare_commit_rows(all_prs)
        counts['commits'] = self._insert_rows('commits', commit_rows)
        
        # Insert reviews
        review_rows = self._prepare_review_rows(all_prs)
        counts['reviews'] = self._insert_rows('reviews', review_rows)
        
        # Insert review comments
        review_comment_rows = self._prepare_review_comment_rows(all_prs)
        counts['review_comments'] = self._insert_rows('review_comments', review_comment_rows)
        
        # Insert issue comments
        issue_comment_rows = self._prepare_issue_comment_rows(all_prs)
        counts['issue_comments'] = self._insert_rows('issue_comments', issue_comment_rows)
        
        logger.info(f"Publishing complete: {counts}")
        return counts
    
    def collect_and_publish(self,
                           since: Optional[datetime] = None,
                           until: Optional[datetime] = None,
                           repo_filter: Optional[List[str]] = None) -> Dict[str, int]:
        """
        Collect data from GitHub and publish to BigQuery
        
        Args:
            since: Only collect data updated after this date
            until: Only collect data updated before this date
            repo_filter: Optional list of repository names to collect
        
        Returns:
            Dictionary with counts of inserted rows per table
        """
        logger.info(f"Starting collection for organization: {self.config.github_org}")
        logger.info(f"Date range: {since} to {until}")
        
        # Fetch data from GitHub
        pr_data = self.fetcher.fetch_organization_prs(
            self.config.github_org,
            since=since,
            until=until,
            parallel=True,
            repo_filter=repo_filter
        )
        
        # Publish to BigQuery
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

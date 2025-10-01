"""
GCP Storage Module
Handles persistence of GitHub data to GCP buckets
"""
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from google.cloud import storage
from google.cloud.exceptions import NotFound

logger = logging.getLogger(__name__)


class GCSStorage:
    """Manages data persistence to Google Cloud Storage"""
    
    def __init__(self, bucket_name: str, project_id: Optional[str] = None):
        self.bucket_name = bucket_name
        self.client = storage.Client(project=project_id)
        self.bucket = None
        self._ensure_bucket()
    
    def _ensure_bucket(self):
        """Ensure the bucket exists"""
        try:
            self.bucket = self.client.get_bucket(self.bucket_name)
            logger.info(f"Using existing bucket: {self.bucket_name}")
        except NotFound:
            logger.info(f"Creating bucket: {self.bucket_name}")
            self.bucket = self.client.create_bucket(self.bucket_name)
    
    def _get_blob_path(self, org: str, repo: str, data_type: str, 
                       timestamp: str, chunk_id: int = 0) -> str:
        """Generate blob path for data"""
        # Format: org/repo/data_type/YYYY-MM-DD/timestamp_chunk.json
        date_str = timestamp.split('T')[0]
        return f"{org}/{repo}/{data_type}/{date_str}/{timestamp}_chunk_{chunk_id}.json"
    
    def _get_checkpoint_path(self, org: str, collection_id: str) -> str:
        """Generate checkpoint path"""
        return f"{org}/_checkpoints/{collection_id}.json"
    
    def write_pr_data(self, org: str, repo: str, pr_data: List[Dict[str, Any]], 
                     timestamp: Optional[str] = None) -> str:
        """
        Write PR data to bucket
        
        Returns:
            Path to the written blob
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()
        
        blob_path = self._get_blob_path(org, repo, "pull_requests", timestamp)
        blob = self.bucket.blob(blob_path)
        
        # Write data as JSON
        data = {
            "organization": org,
            "repository": repo,
            "data_type": "pull_requests",
            "timestamp": timestamp,
            "count": len(pr_data),
            "data": pr_data
        }
        
        blob.upload_from_string(
            json.dumps(data, indent=2, default=str),
            content_type='application/json'
        )
        
        logger.info(f"Wrote {len(pr_data)} PRs to {blob_path}")
        return blob_path
    
    def write_data_chunks(self, org: str, repo: str, data_type: str,
                         data: List[Dict[str, Any]], chunk_size: int = 100,
                         timestamp: Optional[str] = None) -> List[str]:
        """
        Write data in chunks to bucket
        
        Returns:
            List of blob paths
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()
        
        blob_paths = []
        
        # Split data into chunks
        for i in range(0, len(data), chunk_size):
            chunk = data[i:i + chunk_size]
            chunk_id = i // chunk_size
            
            blob_path = self._get_blob_path(org, repo, data_type, timestamp, chunk_id)
            blob = self.bucket.blob(blob_path)
            
            chunk_data = {
                "organization": org,
                "repository": repo,
                "data_type": data_type,
                "timestamp": timestamp,
                "chunk_id": chunk_id,
                "count": len(chunk),
                "data": chunk
            }
            
            blob.upload_from_string(
                json.dumps(chunk_data, indent=2, default=str),
                content_type='application/json'
            )
            
            blob_paths.append(blob_path)
            logger.debug(f"Wrote chunk {chunk_id} ({len(chunk)} items) to {blob_path}")
        
        logger.info(f"Wrote {len(data)} {data_type} items in {len(blob_paths)} chunks")
        return blob_paths
    
    def read_blob(self, blob_path: str) -> Optional[Dict[str, Any]]:
        """Read data from a blob"""
        try:
            blob = self.bucket.blob(blob_path)
            content = blob.download_as_string()
            return json.loads(content)
        except NotFound:
            logger.warning(f"Blob not found: {blob_path}")
            return None
        except Exception as e:
            logger.error(f"Error reading blob {blob_path}: {e}")
            return None
    
    def list_blobs(self, prefix: str) -> List[str]:
        """List all blobs with a given prefix"""
        blobs = self.client.list_blobs(self.bucket_name, prefix=prefix)
        return [blob.name for blob in blobs]
    
    def list_repositories(self, org: str, data_type: str = "pull_requests") -> List[str]:
        """List all repositories that have data"""
        prefix = f"{org}/"
        blobs = self.list_blobs(prefix)
        
        repos = set()
        for blob in blobs:
            parts = blob.split('/')
            if len(parts) >= 3 and parts[2] == data_type:
                repos.add(parts[1])
        
        return sorted(repos)
    
    def list_data_files(self, org: str, repo: str, data_type: str,
                       date_filter: Optional[str] = None) -> List[str]:
        """
        List all data files for a repository and data type
        
        Args:
            org: Organization name
            repo: Repository name
            data_type: Type of data (pull_requests, commits, etc.)
            date_filter: Optional date filter (YYYY-MM-DD)
        
        Returns:
            List of blob paths
        """
        if date_filter:
            prefix = f"{org}/{repo}/{data_type}/{date_filter}/"
        else:
            prefix = f"{org}/{repo}/{data_type}/"
        
        return self.list_blobs(prefix)
    
    def write_checkpoint(self, org: str, collection_id: str, 
                        checkpoint_data: Dict[str, Any]) -> str:
        """
        Write a checkpoint for resumable collection
        
        Args:
            org: Organization name
            collection_id: Unique identifier for this collection run
            checkpoint_data: Data to checkpoint (e.g., completed repos, current state)
        
        Returns:
            Path to checkpoint blob
        """
        checkpoint_path = self._get_checkpoint_path(org, collection_id)
        blob = self.bucket.blob(checkpoint_path)
        
        checkpoint = {
            "organization": org,
            "collection_id": collection_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": checkpoint_data
        }
        
        blob.upload_from_string(
            json.dumps(checkpoint, indent=2, default=str),
            content_type='application/json'
        )
        
        logger.info(f"Wrote checkpoint to {checkpoint_path}")
        return checkpoint_path
    
    def read_checkpoint(self, org: str, collection_id: str) -> Optional[Dict[str, Any]]:
        """Read a checkpoint"""
        checkpoint_path = self._get_checkpoint_path(org, collection_id)
        return self.read_blob(checkpoint_path)
    
    def delete_blob(self, blob_path: str) -> bool:
        """Delete a blob"""
        try:
            blob = self.bucket.blob(blob_path)
            blob.delete()
            logger.info(f"Deleted blob: {blob_path}")
            return True
        except Exception as e:
            logger.error(f"Error deleting blob {blob_path}: {e}")
            return False
    
    def delete_repository_data(self, org: str, repo: str, 
                              data_type: Optional[str] = None) -> int:
        """
        Delete all data for a repository
        
        Args:
            org: Organization name
            repo: Repository name
            data_type: Optional data type to delete (if None, delete all)
        
        Returns:
            Number of blobs deleted
        """
        if data_type:
            prefix = f"{org}/{repo}/{data_type}/"
        else:
            prefix = f"{org}/{repo}/"
        
        blobs = self.list_blobs(prefix)
        count = 0
        
        for blob_path in blobs:
            if self.delete_blob(blob_path):
                count += 1
        
        logger.info(f"Deleted {count} blobs for {org}/{repo}")
        return count
    
    def get_data_summary(self, org: str) -> Dict[str, Any]:
        """Get summary of stored data"""
        summary = {
            "organization": org,
            "repositories": {},
            "total_files": 0,
            "total_size_bytes": 0
        }
        
        prefix = f"{org}/"
        blobs = self.client.list_blobs(self.bucket_name, prefix=prefix)
        
        for blob in blobs:
            parts = blob.name.split('/')
            if len(parts) < 3:
                continue
            
            repo = parts[1]
            if repo == "_checkpoints":
                continue
            
            data_type = parts[2]
            
            if repo not in summary["repositories"]:
                summary["repositories"][repo] = {}
            
            if data_type not in summary["repositories"][repo]:
                summary["repositories"][repo][data_type] = {
                    "file_count": 0,
                    "size_bytes": 0
                }
            
            summary["repositories"][repo][data_type]["file_count"] += 1
            summary["repositories"][repo][data_type]["size_bytes"] += blob.size
            summary["total_files"] += 1
            summary["total_size_bytes"] += blob.size
        
        return summary


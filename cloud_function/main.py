"""
Cloud Function Entry Point for GitHub Stats Collector

This function is triggered by Cloud Scheduler every hour to collect
GitHub statistics and publish them to BigQuery via GCS.
"""
import os
import logging
from datetime import datetime, timezone, timedelta
import functions_framework
from flask import jsonify

# Import from parent directory
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from modules.collector import GitHubCollector

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@functions_framework.http
def collect_github_stats(request):
    """
    HTTP Cloud Function to collect GitHub statistics.
    
    This function is triggered by Cloud Scheduler on an hourly basis.
    It collects data from the last hour (with a small overlap to ensure
    no data is missed) and publishes to BigQuery via GCS.
    
    Args:
        request: The HTTP request object
    
    Returns:
        JSON response with collection statistics
    """
    try:
        logger.info("Starting GitHub stats collection")
        
        # Load configuration from environment
        config = Config.from_env()
        logger.info(f"Configuration loaded for organization: {config.github_org}")
        
        # Create collector
        collector = GitHubCollector(config)
        
        # Ensure BigQuery schema is initialized
        try:
            collector.initialize_bigquery()
        except Exception as e:
            logger.warning(f"Schema initialization warning (may already exist): {e}")
        
        # Determine collection window
        # Collect last 2 hours to ensure no data is missed (with overlap)
        # The upsert logic will prevent duplicates
        until = datetime.now(timezone.utc)
        since = until - timedelta(hours=2)
        
        logger.info(f"Collecting data from {since} to {until}")
        
        # Perform collection with deduplication
        counts = collector.collect_and_publish(
            since=since,
            until=until,
            collection_id=until.isoformat(),
            resume=False  # Don't resume in scheduled mode
        )
        
        # Prepare response
        response = {
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "organization": config.github_org,
            "collection_window": {
                "since": since.isoformat(),
                "until": until.isoformat()
            },
            "counts": counts,
            "message": "GitHub stats collected successfully"
        }
        
        logger.info(f"Collection complete: {counts}")
        return jsonify(response), 200
        
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return jsonify({
            "status": "error",
            "error": "Configuration error",
            "message": str(e)
        }), 500
        
    except Exception as e:
        logger.error(f"Collection error: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": "Collection failed",
            "message": str(e)
        }), 500


@functions_framework.http
def collect_github_stats_pubsub(request):
    """
    HTTP Cloud Function triggered by Pub/Sub via Cloud Scheduler.
    
    This is an alternative entry point if you prefer Pub/Sub triggers.
    
    Args:
        request: The HTTP request object (from Pub/Sub push)
    
    Returns:
        Empty response (200 OK)
    """
    try:
        # Pub/Sub message is in request body
        import json
        import base64
        
        envelope = request.get_json()
        if envelope and 'message' in envelope:
            message = envelope['message']
            if 'data' in message:
                data = base64.b64decode(message['data']).decode('utf-8')
                logger.info(f"Received Pub/Sub message: {data}")
        
        # Call the main collection function
        result = collect_github_stats(request)
        
        # For Pub/Sub, we just need to return 200
        return ('', 200)
        
    except Exception as e:
        logger.error(f"Pub/Sub handler error: {e}", exc_info=True)
        return ('', 500)


@functions_framework.http
def manual_trigger(request):
    """
    HTTP Cloud Function for manual triggering with custom parameters.
    
    Query parameters:
        - hours: Number of hours to look back (default: 2)
        - repos: Comma-separated list of repositories (optional)
        - resume: Collection ID to resume (optional)
    
    Example:
        curl "https://REGION-PROJECT.cloudfunctions.net/manual_trigger?hours=24&repos=frontend,backend"
    
    Args:
        request: The HTTP request object
    
    Returns:
        JSON response with collection statistics
    """
    try:
        logger.info("Starting manual GitHub stats collection")
        
        # Parse query parameters
        hours = int(request.args.get('hours', 2))
        repos = request.args.get('repos')
        collection_id = request.args.get('resume')
        
        repo_filter = None
        if repos:
            repo_filter = [r.strip() for r in repos.split(',')]
            logger.info(f"Repository filter: {repo_filter}")
        
        # Load configuration
        config = Config.from_env()
        logger.info(f"Configuration loaded for organization: {config.github_org}")
        
        # Create collector
        collector = GitHubCollector(config)
        
        # Ensure BigQuery schema is initialized
        try:
            collector.initialize_bigquery()
        except Exception as e:
            logger.warning(f"Schema initialization warning: {e}")
        
        # Determine collection window
        until = datetime.now(timezone.utc)
        since = until - timedelta(hours=hours)
        
        logger.info(f"Collecting data from {since} to {until}")
        
        # Perform collection
        if collection_id:
            # Resume mode
            logger.info(f"Resuming collection: {collection_id}")
            counts = collector.collect_and_publish(
                since=since,
                until=until,
                repo_filter=repo_filter,
                collection_id=collection_id,
                resume=True
            )
        else:
            # Normal collection
            counts = collector.collect_and_publish(
                since=since,
                until=until,
                repo_filter=repo_filter,
                collection_id=until.isoformat(),
                resume=False
            )
        
        # Prepare response
        response = {
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "organization": config.github_org,
            "collection_window": {
                "since": since.isoformat(),
                "until": until.isoformat(),
                "hours": hours
            },
            "filters": {
                "repositories": repo_filter
            },
            "counts": counts,
            "message": "Manual collection completed successfully"
        }
        
        logger.info(f"Manual collection complete: {counts}")
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Manual collection error: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": "Manual collection failed",
            "message": str(e)
        }), 500


#!/usr/bin/env python3
"""
GitHub Stats Collector - Main Entry Point

This is the main entry point for the GitHub stats collector application.
It supports different modes: initialization, backfill, and incremental collection.
"""
import argparse
import logging
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional

from config import Config
from modules.collector import GitHubCollector


def setup_logging(verbose: bool = False):
    """Configure logging"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('github_collector.log')
        ]
    )


def initialize_command(config: Config):
    """Initialize BigQuery schema"""
    logger = logging.getLogger(__name__)
    logger.info("Initializing BigQuery schema...")
    
    collector = GitHubCollector(config)
    collector.initialize_bigquery()
    
    logger.info("Initialization complete!")


def backfill_command(config: Config, days: int, repos: Optional[str] = None):
    """Backfill historical data"""
    logger = logging.getLogger(__name__)
    logger.info(f"Starting backfill for {days} days...")
    
    repo_filter = None
    if repos:
        repo_filter = [r.strip() for r in repos.split(',')]
        logger.info(f"Filtering repositories: {repo_filter}")
    
    collector = GitHubCollector(config)
    
    # Ensure schema is initialized
    collector.initialize_bigquery()
    
    # Run backfill
    counts = collector.backfill(days=days, repo_filter=repo_filter)
    
    logger.info("Backfill complete!")
    logger.info(f"Summary: {counts}")


def collect_command(config: Config, 
                   since: Optional[str] = None,
                   until: Optional[str] = None,
                   hours: Optional[int] = None,
                   repos: Optional[str] = None):
    """Collect data for a specific date range or time period"""
    logger = logging.getLogger(__name__)
    
    repo_filter = None
    if repos:
        repo_filter = [r.strip() for r in repos.split(',')]
        logger.info(f"Filtering repositories: {repo_filter}")
    
    collector = GitHubCollector(config)
    
    # Ensure schema is initialized
    collector.initialize_bigquery()
    
    # Determine date range
    if hours:
        logger.info(f"Collecting data from last {hours} hours...")
        counts = collector.incremental_collect(hours=hours, repo_filter=repo_filter)
    else:
        since_dt = None
        until_dt = None
        
        if since:
            since_dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
            logger.info(f"Since: {since_dt}")
        
        if until:
            until_dt = datetime.fromisoformat(until.replace('Z', '+00:00'))
            logger.info(f"Until: {until_dt}")
        
        if not since_dt and not until_dt:
            # Default to last 24 hours if no range specified
            until_dt = datetime.now(timezone.utc)
            since_dt = until_dt - timedelta(hours=24)
            logger.info(f"No date range specified, using last 24 hours")
        
        counts = collector.collect_and_publish(
            since=since_dt,
            until=until_dt,
            repo_filter=repo_filter
        )
    
    logger.info("Collection complete!")
    logger.info(f"Summary: {counts}")


def scheduled_command(config: Config, interval: int = 6, repos: Optional[str] = None):
    """Run collection on a scheduled interval"""
    import time
    logger = logging.getLogger(__name__)
    
    repo_filter = None
    if repos:
        repo_filter = [r.strip() for r in repos.split(',')]
        logger.info(f"Filtering repositories: {repo_filter}")
    
    collector = GitHubCollector(config)
    
    # Ensure schema is initialized
    collector.initialize_bigquery()
    
    logger.info(f"Starting scheduled collection (every {interval} hours)")
    logger.info("Press Ctrl+C to stop")
    
    try:
        while True:
            logger.info("Starting collection cycle...")
            try:
                counts = collector.incremental_collect(hours=interval, repo_filter=repo_filter)
                logger.info(f"Collection cycle complete: {counts}")
            except Exception as e:
                logger.error(f"Error during collection cycle: {e}", exc_info=True)
            
            logger.info(f"Sleeping for {interval} hours...")
            time.sleep(interval * 3600)
    
    except KeyboardInterrupt:
        logger.info("Scheduled collection stopped by user")


def load_gcs_command(config: Config, repo: Optional[str] = None, 
                    date: Optional[str] = None):
    """Load data from GCS and publish to BigQuery"""
    logger = logging.getLogger(__name__)
    
    if not config.persist_to_gcs:
        logger.error("GCS persistence is not enabled. Set PERSIST_TO_GCS=true")
        sys.exit(1)
    
    collector = GitHubCollector(config)
    
    # Ensure schema is initialized
    collector.initialize_bigquery()
    
    logger.info("Loading data from GCS and publishing to BigQuery...")
    counts = collector.load_from_gcs_and_publish(repo=repo, date_filter=date)
    
    logger.info("Load complete!")
    logger.info(f"Summary: {counts}")


def gcs_summary_command(config: Config):
    """Show summary of data in GCS"""
    logger = logging.getLogger(__name__)
    
    if not config.persist_to_gcs:
        logger.error("GCS persistence is not enabled. Set PERSIST_TO_GCS=true")
        sys.exit(1)
    
    from utils.storage import GCSStorage
    storage = GCSStorage(config.gcs_bucket_name, config.bigquery_project_id)
    
    logger.info("Fetching GCS data summary...")
    summary = storage.get_data_summary(config.github_org)
    
    import json
    print("\n" + "="*80)
    print("GCS DATA SUMMARY")
    print("="*80)
    print(json.dumps(summary, indent=2))
    print("="*80)


def wipe_gcs_command(config: Config, repo: str, confirm: bool = False):
    """Wipe GCS data for a repository"""
    logger = logging.getLogger(__name__)
    
    if not config.persist_to_gcs:
        logger.error("GCS persistence is not enabled. Set PERSIST_TO_GCS=true")
        sys.exit(1)
    
    if not confirm:
        logger.error("This is a destructive operation. Use --confirm to proceed.")
        logger.error(f"This will delete ALL data for {repo} from GCS bucket {config.gcs_bucket_name}")
        sys.exit(1)
    
    from utils.storage import GCSStorage
    storage = GCSStorage(config.gcs_bucket_name, config.bigquery_project_id)
    
    logger.warning(f"Deleting all data for {config.github_org}/{repo}...")
    count = storage.delete_repository_data(config.github_org, repo)
    
    logger.info(f"Deleted {count} files from GCS")


def resume_command(config: Config, collection_id: str, repos: Optional[str] = None):
    """Resume a failed collection using a collection ID"""
    logger = logging.getLogger(__name__)
    
    if not config.persist_to_gcs:
        logger.error("GCS persistence is not enabled. Set PERSIST_TO_GCS=true")
        logger.error("Resume capability requires GCS persistence to be enabled")
        sys.exit(1)
    
    repo_filter = None
    if repos:
        repo_filter = [r.strip() for r in repos.split(',')]
        logger.info(f"Filtering repositories: {repo_filter}")
    
    collector = GitHubCollector(config)
    
    # Ensure schema is initialized
    collector.initialize_bigquery()
    
    logger.info(f"Resuming collection with ID: {collection_id}")
    
    # Check if checkpoint exists
    if collector.storage:
        checkpoint = collector.storage.read_checkpoint(config.github_org, collection_id)
        if checkpoint:
            logger.info(f"Found checkpoint: {checkpoint.get('data', {}).get('completed_repos', [])}")
        else:
            logger.warning(f"No checkpoint found for collection ID: {collection_id}")
            logger.info("Will start fresh collection instead")
    
    # Try to parse collection_id as datetime for date range
    try:
        collection_dt = datetime.fromisoformat(collection_id.replace('Z', '+00:00'))
        # Use a reasonable time window around the collection time
        since = collection_dt - timedelta(hours=24)
        until = collection_dt + timedelta(hours=24)
    except:
        # Default to last 24 hours
        until = datetime.now(timezone.utc)
        since = until - timedelta(hours=24)
        logger.warning("Could not parse collection_id as datetime, using last 24 hours")
    
    counts = collector.collect_and_publish(
        since=since,
        until=until,
        repo_filter=repo_filter,
        collection_id=collection_id,
        resume=True
    )
    
    logger.info("Resume complete!")
    logger.info(f"Summary: {counts}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='GitHub Stats Collector - Collect and analyze GitHub repository statistics',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Initialize BigQuery schema
  python main.py init

  # Backfill last 6 months of data (persists to GCS first)
  python main.py backfill --days 180

  # Backfill specific repositories
  python main.py backfill --days 90 --repos "repo1,repo2,repo3"

  # Collect data from a specific date range
  python main.py collect --since 2025-01-01 --until 2025-03-31

  # Collect data from last 12 hours
  python main.py collect --hours 12

  # Run scheduled collection every 6 hours
  python main.py scheduled --interval 6

  # Load data from GCS to BigQuery (for reingestion)
  python main.py load-gcs

  # Load specific repository from GCS
  python main.py load-gcs --repo my-repo --date 2025-01-01

  # Show GCS data summary
  python main.py gcs-summary

  # Wipe GCS data for a repository
  python main.py wipe-gcs --repo my-repo --confirm

  # Resume a failed collection
  python main.py resume --collection-id 2025-01-01T12:00:00+00:00

Environment Variables:
  GITHUB_TOKEN          GitHub personal access token (required)
  BIGQUERY_PROJECT_ID   BigQuery project ID (required)
  BIGQUERY_DATASET_ID   BigQuery dataset ID (default: github_stats)
  GCS_BUCKET_NAME       GCS bucket name (default: github-stats-data)
  PERSIST_TO_GCS        Persist to GCS before BigQuery (default: true)
  GITHUB_ORG            GitHub organization name (default: askscio)
  MAX_WORKERS           Number of parallel workers (default: 10)
        '''
    )
    
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose logging')
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Initialize command
    init_parser = subparsers.add_parser('init', help='Initialize BigQuery schema')
    
    # Backfill command
    backfill_parser = subparsers.add_parser('backfill', 
                                            help='Backfill historical data')
    backfill_parser.add_argument('--days', type=int, default=180,
                                help='Number of days to backfill (default: 180)')
    backfill_parser.add_argument('--repos', type=str,
                                help='Comma-separated list of repositories to backfill')
    
    # Collect command
    collect_parser = subparsers.add_parser('collect',
                                          help='Collect data for a date range')
    collect_parser.add_argument('--since', type=str,
                               help='Start date (ISO format: 2025-01-01T00:00:00Z)')
    collect_parser.add_argument('--until', type=str,
                               help='End date (ISO format: 2025-01-01T00:00:00Z)')
    collect_parser.add_argument('--hours', type=int,
                               help='Collect data from last N hours')
    collect_parser.add_argument('--repos', type=str,
                               help='Comma-separated list of repositories to collect')
    
    # Scheduled command
    scheduled_parser = subparsers.add_parser('scheduled',
                                            help='Run collection on a schedule')
    scheduled_parser.add_argument('--interval', type=int, default=6,
                                 help='Collection interval in hours (default: 6)')
    scheduled_parser.add_argument('--repos', type=str,
                                 help='Comma-separated list of repositories to collect')
    
    # Load from GCS command
    load_gcs_parser = subparsers.add_parser('load-gcs',
                                           help='Load data from GCS and publish to BigQuery')
    load_gcs_parser.add_argument('--repo', type=str,
                                help='Repository name to load (loads all if not specified)')
    load_gcs_parser.add_argument('--date', type=str,
                                help='Date filter (YYYY-MM-DD)')
    
    # GCS summary command
    summary_parser = subparsers.add_parser('gcs-summary',
                                          help='Show summary of data in GCS bucket')
    
    # Wipe GCS command
    wipe_parser = subparsers.add_parser('wipe-gcs',
                                       help='Wipe GCS data for a repository')
    wipe_parser.add_argument('--repo', type=str, required=True,
                            help='Repository name to wipe')
    wipe_parser.add_argument('--confirm', action='store_true',
                            help='Confirm deletion (required)')
    
    # Resume command
    resume_parser = subparsers.add_parser('resume',
                                         help='Resume a failed collection')
    resume_parser.add_argument('--collection-id', type=str, required=True,
                              help='Collection ID to resume (ISO timestamp)')
    resume_parser.add_argument('--repos', type=str,
                              help='Comma-separated list of repositories to collect')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    # Load configuration
    try:
        config = Config.from_env()
        logger.info(f"Configuration loaded for organization: {config.github_org}")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please set required environment variables (GITHUB_TOKEN, BIGQUERY_PROJECT_ID)")
        sys.exit(1)
    
    # Execute command
    try:
        if args.command == 'init':
            initialize_command(config)
        
        elif args.command == 'backfill':
            backfill_command(config, args.days, args.repos)
        
        elif args.command == 'collect':
            collect_command(config, args.since, args.until, args.hours, args.repos)
        
        elif args.command == 'scheduled':
            scheduled_command(config, args.interval, args.repos)
        
        elif args.command == 'load-gcs':
            load_gcs_command(config, args.repo, args.date)
        
        elif args.command == 'gcs-summary':
            gcs_summary_command(config)
        
        elif args.command == 'wipe-gcs':
            wipe_gcs_command(config, args.repo, args.confirm)
        
        elif args.command == 'resume':
            resume_command(config, args.collection_id, args.repos)
        
        else:
            logger.error(f"Unknown command: {args.command}")
            sys.exit(1)
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

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


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='GitHub Stats Collector - Collect and analyze GitHub repository statistics',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Initialize BigQuery schema
  python main.py init

  # Backfill last 6 months of data
  python main.py backfill --days 180

  # Backfill specific repositories
  python main.py backfill --days 90 --repos "repo1,repo2,repo3"

  # Collect data from a specific date range
  python main.py collect --since 2025-01-01 --until 2025-03-31

  # Collect data from last 12 hours
  python main.py collect --hours 12

  # Run scheduled collection every 6 hours
  python main.py scheduled --interval 6

Environment Variables:
  GITHUB_TOKEN          GitHub personal access token (required)
  BIGQUERY_PROJECT_ID   BigQuery project ID (required)
  BIGQUERY_DATASET_ID   BigQuery dataset ID (default: github_stats)
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
        
        else:
            logger.error(f"Unknown command: {args.command}")
            sys.exit(1)
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

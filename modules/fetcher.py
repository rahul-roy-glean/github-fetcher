"""
GitHub Data Fetcher Module
Fetches commits, PRs, reviews, and other data from GitHub repositories
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict

from utils.github_client import GitHubClient

logger = logging.getLogger(__name__)


@dataclass
class PullRequestData:
    """Structured pull request data"""
    pr_number: int
    title: str
    state: str
    author: str
    author_type: str  # User or Bot
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime]
    merged_at: Optional[datetime]
    repository: str
    organization: str
    url: str
    
    # PR metrics
    additions: int
    deletions: int
    changed_files: int
    
    # Labels
    labels: List[str]
    size_label: Optional[str]  # e.g., "size/S", "size/M", "size/L"
    
    # Commits
    commits: List[Dict[str, Any]]
    commit_count: int
    
    # Reviews
    reviews: List[Dict[str, Any]]
    review_count: int
    
    # Comments
    review_comments: List[Dict[str, Any]]
    review_comment_count: int
    issue_comments: List[Dict[str, Any]]
    issue_comment_count: int
    
    # Additional metadata
    is_draft: bool
    is_merged: bool
    merge_commit_sha: Optional[str]
    base_ref: str
    head_ref: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        # Convert datetime objects to ISO strings
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
        return data


class GitHubFetcher:
    """Fetches data from GitHub repositories"""
    
    def __init__(self, client: GitHubClient, max_workers: int = 10):
        self.client = client
        self.max_workers = max_workers
    
    def fetch_organization_repos(self, org: str) -> List[Dict[str, Any]]:
        """Fetch all repositories for an organization"""
        logger.info(f"Fetching repositories for organization: {org}")
        repos = self.client.get_org_repos(org)
        logger.info(f"Found {len(repos)} repositories")
        return repos
    
    def _extract_size_label(self, labels: List[Dict[str, Any]]) -> Optional[str]:
        """Extract size label from PR labels"""
        for label in labels:
            label_name = label.get('name', '')
            if label_name.startswith('size/'):
                return label_name
        return None
    
    def _fetch_pr_details(self, owner: str, repo: str, pr: Dict[str, Any]) -> Optional[PullRequestData]:
        """Fetch detailed information for a single PR"""
        pr_number = pr['number']
        
        try:
            logger.debug(f"Fetching details for PR #{pr_number} in {owner}/{repo}")
            
            # Fetch commits
            commits = []
            try:
                commits = self.client.get_pr_commits(owner, repo, pr_number)
            except Exception as e:
                logger.warning(f"Could not fetch commits for PR #{pr_number}: {e}")
            
            # Fetch reviews
            reviews = []
            try:
                reviews = self.client.get_pr_reviews(owner, repo, pr_number)
            except Exception as e:
                logger.warning(f"Could not fetch reviews for PR #{pr_number}: {e}")
            
            # Fetch review comments
            review_comments = []
            try:
                review_comments = self.client.get_pr_review_comments(owner, repo, pr_number)
            except Exception as e:
                logger.warning(f"Could not fetch review comments for PR #{pr_number}: {e}")
            
            # Fetch issue comments
            issue_comments = []
            try:
                issue_comments = self.client.get_issue_comments(owner, repo, pr_number)
            except Exception as e:
                logger.warning(f"Could not fetch issue comments for PR #{pr_number}: {e}")
            
            # Extract labels
            labels = [label['name'] for label in pr.get('labels', [])]
            size_label = self._extract_size_label(pr.get('labels', []))
            
            # Determine author type
            author = pr.get('user', {})
            author_name = author.get('login', 'unknown')
            author_type = author.get('type', 'User')
            
            # Parse dates
            created_at = datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00'))
            updated_at = datetime.fromisoformat(pr['updated_at'].replace('Z', '+00:00'))
            
            closed_at = None
            if pr.get('closed_at'):
                closed_at = datetime.fromisoformat(pr['closed_at'].replace('Z', '+00:00'))
            
            merged_at = None
            if pr.get('merged_at'):
                merged_at = datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00'))
            
            return PullRequestData(
                pr_number=pr_number,
                title=pr.get('title', ''),
                state=pr.get('state', 'unknown'),
                author=author_name,
                author_type=author_type,
                created_at=created_at,
                updated_at=updated_at,
                closed_at=closed_at,
                merged_at=merged_at,
                repository=repo,
                organization=owner,
                url=pr.get('html_url', ''),
                additions=pr.get('additions', 0),
                deletions=pr.get('deletions', 0),
                changed_files=pr.get('changed_files', 0),
                labels=labels,
                size_label=size_label,
                commits=commits,
                commit_count=len(commits),
                reviews=reviews,
                review_count=len(reviews),
                review_comments=review_comments,
                review_comment_count=len(review_comments),
                issue_comments=issue_comments,
                issue_comment_count=len(issue_comments),
                is_draft=pr.get('draft', False),
                is_merged=pr.get('merged', False),
                merge_commit_sha=pr.get('merge_commit_sha'),
                base_ref=pr.get('base', {}).get('ref', ''),
                head_ref=pr.get('head', {}).get('ref', ''),
            )
        
        except Exception as e:
            logger.error(f"Error fetching details for PR #{pr_number} in {owner}/{repo}: {e}")
            return None
    
    def fetch_repository_prs(self, owner: str, repo: str, 
                           since: Optional[datetime] = None,
                           until: Optional[datetime] = None,
                           parallel: bool = True) -> List[PullRequestData]:
        """
        Fetch pull requests and their details for a repository
        
        Args:
            owner: Repository owner/organization
            repo: Repository name
            since: Only fetch PRs updated after this date
            until: Only fetch PRs updated before this date
            parallel: Whether to fetch PR details in parallel
        
        Returns:
            List of PullRequestData objects
        """
        logger.info(f"Fetching PRs for {owner}/{repo}")
        
        # Fetch all PRs
        prs = self.client.get_pull_requests(owner, repo, state="all", since=since, until=until)
        logger.info(f"Found {len(prs)} PRs in {owner}/{repo}")
        
        if not prs:
            return []
        
        # Fetch detailed information for each PR
        pr_data_list = []
        
        if parallel and len(prs) > 1:
            # Parallel processing
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_pr = {
                    executor.submit(self._fetch_pr_details, owner, repo, pr): pr
                    for pr in prs
                }
                
                for future in as_completed(future_to_pr):
                    pr_data = future.result()
                    if pr_data:
                        pr_data_list.append(pr_data)
        else:
            # Sequential processing
            for pr in prs:
                pr_data = self._fetch_pr_details(owner, repo, pr)
                if pr_data:
                    pr_data_list.append(pr_data)
        
        logger.info(f"Successfully fetched details for {len(pr_data_list)} PRs")
        return pr_data_list
    
    def fetch_organization_prs(self, org: str,
                              since: Optional[datetime] = None,
                              until: Optional[datetime] = None,
                              parallel: bool = True,
                              repo_filter: Optional[List[str]] = None) -> Dict[str, List[PullRequestData]]:
        """
        Fetch pull requests for all repositories in an organization
        
        Args:
            org: Organization name
            since: Only fetch PRs updated after this date
            until: Only fetch PRs updated before this date
            parallel: Whether to fetch data in parallel
            repo_filter: Optional list of repository names to fetch (if None, fetch all)
        
        Returns:
            Dictionary mapping repository names to lists of PullRequestData
        """
        logger.info(f"Fetching PRs for organization: {org}")
        
        # Get all repositories
        repos = self.fetch_organization_repos(org)
        
        # Filter repositories if specified
        if repo_filter:
            repos = [r for r in repos if r['name'] in repo_filter]
            logger.info(f"Filtered to {len(repos)} repositories")
        
        all_prs = {}
        
        if parallel and len(repos) > 1:
            # Parallel processing across repositories
            with ThreadPoolExecutor(max_workers=min(self.max_workers, len(repos))) as executor:
                future_to_repo = {
                    executor.submit(
                        self.fetch_repository_prs,
                        org,
                        repo['name'],
                        since,
                        until,
                        parallel=True  # Also parallelize within each repo
                    ): repo['name']
                    for repo in repos
                }
                
                for future in as_completed(future_to_repo):
                    repo_name = future_to_repo[future]
                    try:
                        prs = future.result()
                        all_prs[repo_name] = prs
                        logger.info(f"Fetched {len(prs)} PRs from {repo_name}")
                    except Exception as e:
                        logger.error(f"Error fetching PRs from {repo_name}: {e}")
                        all_prs[repo_name] = []
        else:
            # Sequential processing
            for repo in repos:
                repo_name = repo['name']
                try:
                    prs = self.fetch_repository_prs(org, repo_name, since, until, parallel=False)
                    all_prs[repo_name] = prs
                    logger.info(f"Fetched {len(prs)} PRs from {repo_name}")
                except Exception as e:
                    logger.error(f"Error fetching PRs from {repo_name}: {e}")
                    all_prs[repo_name] = []
        
        total_prs = sum(len(prs) for prs in all_prs.values())
        logger.info(f"Fetched total of {total_prs} PRs from {len(all_prs)} repositories")
        
        return all_prs


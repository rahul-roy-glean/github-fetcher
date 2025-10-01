"""
GitHub API Client with rate limiting support
"""
import time
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class RateLimiter:
    """Handles GitHub API rate limiting"""
    
    def __init__(self, max_requests_per_hour: int = 4500):
        self.max_requests_per_hour = max_requests_per_hour
        self.requests_made = 0
        self.window_start = time.time()
        self.remaining = None
        self.reset_time = None
    
    def wait_if_needed(self):
        """Wait if we're approaching rate limits"""
        current_time = time.time()
        
        # Reset counter if we're in a new hour
        if current_time - self.window_start >= 3600:
            self.requests_made = 0
            self.window_start = current_time
        
        # Check if we need to wait based on GitHub's rate limit info
        if self.remaining is not None and self.remaining < 100:
            if self.reset_time and self.reset_time > current_time:
                wait_time = self.reset_time - current_time + 1
                logger.warning(f"Rate limit low ({self.remaining} remaining). Waiting {wait_time:.0f}s")
                time.sleep(wait_time)
                self.requests_made = 0
                return
        
        # Check if we're making too many requests per hour
        if self.requests_made >= self.max_requests_per_hour:
            elapsed = current_time - self.window_start
            if elapsed < 3600:
                wait_time = 3600 - elapsed
                logger.warning(f"Local rate limit reached. Waiting {wait_time:.0f}s")
                time.sleep(wait_time)
                self.requests_made = 0
                self.window_start = time.time()
    
    def update_from_headers(self, headers: Dict[str, str]):
        """Update rate limit info from response headers"""
        try:
            self.remaining = int(headers.get('X-RateLimit-Remaining', 5000))
            self.reset_time = int(headers.get('X-RateLimit-Reset', 0))
        except (ValueError, TypeError):
            pass
        
        self.requests_made += 1


class GitHubClient:
    """GitHub API client with rate limiting and retry logic"""
    
    def __init__(self, token: str, max_requests_per_hour: int = 4500):
        self.token = token
        self.base_url = "https://api.github.com"
        self.rate_limiter = RateLimiter(max_requests_per_hour)
        
        # Setup session with retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=5,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        
        self.session.headers.update({
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        })
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make a request with rate limiting"""
        self.rate_limiter.wait_if_needed()
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self.session.request(method, url, **kwargs)
        
        # Update rate limiter with response headers
        self.rate_limiter.update_from_headers(response.headers)
        
        response.raise_for_status()
        return response
    
    def get(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make a GET request"""
        response = self._make_request("GET", endpoint, **kwargs)
        return response.json()
    
    def get_paginated(self, endpoint: str, params: Optional[Dict] = None, 
                     max_pages: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all pages of a paginated endpoint"""
        if params is None:
            params = {}
        
        params.setdefault('per_page', 100)
        
        results = []
        page = 1
        
        while True:
            if max_pages and page > max_pages:
                break
            
            params['page'] = page
            response = self._make_request("GET", endpoint, params=params)
            data = response.json()
            
            if not data:
                break
            
            results.extend(data if isinstance(data, list) else [data])
            
            # Check if there's a next page
            if 'Link' not in response.headers:
                break
            
            links = response.headers['Link']
            if 'rel="next"' not in links:
                break
            
            page += 1
            logger.debug(f"Fetching page {page} of {endpoint}")
        
        return results
    
    def get_org_repos(self, org: str) -> List[Dict[str, Any]]:
        """Get all repositories for an organization"""
        logger.info(f"Fetching repositories for organization: {org}")
        return self.get_paginated(f"/orgs/{org}/repos", params={"type": "all"})
    
    def get_pull_requests(self, owner: str, repo: str, 
                         state: str = "all",
                         since: Optional[datetime] = None,
                         until: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get pull requests for a repository"""
        logger.info(f"Fetching PRs for {owner}/{repo} (state={state})")
        
        params = {
            "state": state,
            "sort": "updated",
            "direction": "desc",
        }
        
        prs = self.get_paginated(f"/repos/{owner}/{repo}/pulls", params=params)
        
        # Filter by date if specified
        if since or until:
            filtered_prs = []
            for pr in prs:
                updated_at = datetime.fromisoformat(pr['updated_at'].replace('Z', '+00:00'))
                
                if since and updated_at < since:
                    continue
                if until and updated_at > until:
                    continue
                
                filtered_prs.append(pr)
            
            return filtered_prs
        
        return prs
    
    def get_pr_commits(self, owner: str, repo: str, pr_number: int) -> List[Dict[str, Any]]:
        """Get commits for a pull request"""
        return self.get_paginated(f"/repos/{owner}/{repo}/pulls/{pr_number}/commits")
    
    def get_pr_reviews(self, owner: str, repo: str, pr_number: int) -> List[Dict[str, Any]]:
        """Get reviews for a pull request"""
        return self.get_paginated(f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews")
    
    def get_pr_review_comments(self, owner: str, repo: str, pr_number: int) -> List[Dict[str, Any]]:
        """Get review comments for a pull request"""
        return self.get_paginated(f"/repos/{owner}/{repo}/pulls/{pr_number}/comments")
    
    def get_issue_comments(self, owner: str, repo: str, issue_number: int) -> List[Dict[str, Any]]:
        """Get issue comments (includes PR comments)"""
        return self.get_paginated(f"/repos/{owner}/{repo}/issues/{issue_number}/comments")
    
    def get_commit_details(self, owner: str, repo: str, sha: str) -> Dict[str, Any]:
        """Get detailed information about a commit"""
        return self.get(f"/repos/{owner}/{repo}/commits/{sha}")
    
    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limit status"""
        return self.get("/rate_limit")


"""
Async JIRA client module for the MCP server.
Handles async interactions with the JIRA API using aiohttp.
"""
import os
import asyncio
import json
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, quote
import aiohttp
from asyncio_throttle import Throttler
import logging

logger = logging.getLogger(__name__)

class AsyncJiraClient:
    """
    Async client for interacting with JIRA API.
    Handles authentication and provides async methods for working with JIRA issues.
    """

    def __init__(self, server_url: str, api_token: str, max_concurrent_requests: int = 2):
        """
        Initialize an async JIRA client with the provided credentials.

        Args:
            server_url: URL of the JIRA server
            api_token: JIRA API token for authentication
            max_concurrent_requests: Maximum number of concurrent requests
        """
        self.server_url = server_url.rstrip('/')
        self.api_token = api_token
        self.max_concurrent_requests = max_concurrent_requests
        
        # Create throttler for rate limiting using max_concurrent_requests
        self.throttler = Throttler(rate_limit=max_concurrent_requests, period=1.0)
        
        # Connection pooling configuration
        connector = aiohttp.TCPConnector(
            limit=20,  # Total connection pool size
            limit_per_host=10,  # Max connections per host
            ttl_dns_cache=300,  # DNS cache TTL
            use_dns_cache=True,
        )
        
        # Request timeout configuration with defaults
        request_timeout = int(os.getenv('REQUEST_TIMEOUT', '30'))
        connect_timeout = int(os.getenv('CONNECT_TIMEOUT', '10'))
        
        timeout = aiohttp.ClientTimeout(
            total=request_timeout,
            connect=connect_timeout
        )
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        )

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make an HTTP request with rate limiting and retry logic."""
        url = f"{self.server_url}{endpoint}"
        max_retries = 3
        base_delay = 1.0
        
        for attempt in range(max_retries + 1):
            try:
                # Apply rate limiting
                async with self.throttler:
                    async with self.session.request(method, url, **kwargs) as response:
                        # Handle rate limiting with exponential backoff
                        if response.status == 429:
                            retry_after = response.headers.get('Retry-After')
                            if retry_after:
                                delay = float(retry_after)
                            else:
                                # Exponential backoff: 1s, 2s, 4s, 8s
                                delay = base_delay * (2 ** attempt)
                            
                            logger.warning(f"Rate limited (429). Waiting {delay}s before retry {attempt + 1}/{max_retries}")
                            
                            if attempt < max_retries:
                                await asyncio.sleep(delay)
                                continue
                            else:
                                raise Exception(f"Rate limited after {max_retries} retries. Try reducing MAX_CONCURRENT_REQUESTS.")
                        
                        # Handle other HTTP errors
                        if response.status >= 400:
                            error_text = await response.text()
                            raise Exception(f"JIRA API request failed: {response.status}, message='{response.reason}', url='{url}', response='{error_text[:200]}'")
                        
                        # Log rate limit headers for monitoring
                        remaining = response.headers.get('X-RateLimit-Remaining')
                        limit = response.headers.get('X-RateLimit-Limit')
                        if remaining and limit:
                            logger.debug(f"Rate limit: {remaining}/{limit} remaining")
                        
                        return await response.json()
                        
            except aiohttp.ClientError as e:
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Request failed (attempt {attempt + 1}/{max_retries + 1}): {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise Exception(f"Request failed after {max_retries + 1} attempts: {e}")
            except Exception as e:
                # Don't retry on non-network errors
                raise e
        
        raise Exception(f"Request failed after {max_retries + 1} attempts")

    async def search_issues(self, jql: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Search for issues using JQL (JIRA Query Language).

        Args:
            jql: JQL query string
            max_results: Maximum number of results to return

        Returns:
            List of issues matching the query
        """
        params = {
            'jql': jql,
            'maxResults': max_results,
            'fields': 'summary,status,assignee,priority,issuetype,created,updated,description'
        }
        
        response = await self._make_request('GET', '/rest/api/2/search', params=params)
        return response.get('issues', [])

    async def get_issue(self, issue_key: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific issue.

        Args:
            issue_key: The issue key (e.g., PROJECT-123)

        Returns:
            Detailed issue information
        """
        endpoint = f'/rest/api/2/issue/{issue_key}'
        params = {
            # Note: 'subtasks' field removed from main request as it's not searchable in some JIRA instances
            # Subtasks are retrieved separately via get_subtasks() method when needed
            'fields': 'summary,status,assignee,priority,issuetype,created,updated,description,comment,issuelinks'
        }
        
        return await self._make_request('GET', endpoint, params=params)

    async def get_issue_comments(self, issue_key: str) -> List[Dict[str, Any]]:
        """
        Get all comments for a specific issue.

        Args:
            issue_key: The issue key (e.g., PROJECT-123)

        Returns:
            List of comments for the issue
        """
        endpoint = f'/rest/api/2/issue/{issue_key}/comment'
        
        response = await self._make_request('GET', endpoint)
        return response.get('comments', [])

    async def get_issue_links(self, issue_key: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all links for a specific issue, categorized by link type.

        Args:
            issue_key: The issue key (e.g., PROJECT-123)

        Returns:
            Dictionary of link types to lists of linked issues
        """
        issue = await self.get_issue(issue_key)
        
        links_by_type = {}
        issue_links = issue.get('fields', {}).get('issuelinks', [])
        
        for link in issue_links:
            link_type = link.get('type', {}).get('name', 'Unknown')
            
            if link_type not in links_by_type:
                links_by_type[link_type] = []
            
            # Determine if this issue is the inward or outward link
            if 'outwardIssue' in link:
                linked_issue = link['outwardIssue']
                direction = 'outward'
            elif 'inwardIssue' in link:
                linked_issue = link['inwardIssue']
                direction = 'inward'
            else:
                continue
            
            links_by_type[link_type].append({
                'key': linked_issue.get('key'),
                'summary': linked_issue.get('fields', {}).get('summary'),
                'status': linked_issue.get('fields', {}).get('status', {}).get('name'),
                'direction': direction
            })
        
        return links_by_type

    async def get_epic_issues(self, epic_key: str) -> List[Dict[str, Any]]:
        """
        Get all issues that belong to a specific epic.

        Args:
            epic_key: The epic issue key (e.g., PROJECT-123)

        Returns:
            List of issues in the epic
        """
        # Use JQL to find issues in the epic
        jql = f'"Epic Link" = {epic_key}'
        return await self.search_issues(jql)

    async def get_subtasks(self, issue_key: str) -> List[Dict[str, Any]]:
        """
        Get all subtasks for a specific issue.

        Args:
            issue_key: The parent issue key (e.g., PROJECT-123)

        Returns:
            List of subtasks for the issue
        """
        # Make a specific request for subtasks field only
        endpoint = f'/rest/api/2/issue/{issue_key}'
        params = {
            'fields': 'subtasks'
        }
        
        issue = await self._make_request('GET', endpoint, params=params)
        return issue.get('fields', {}).get('subtasks', [])

    async def get_available_transitions(self, issue_key: str) -> List[Dict[str, Any]]:
        """
        Get all available transitions for a specific issue.

        Args:
            issue_key: The issue key (e.g., PROJECT-123)

        Returns:
            List of available transitions for the issue
        """
        endpoint = f'/rest/api/2/issue/{issue_key}/transitions'
        
        try:
            response = await self._make_request('GET', endpoint)
            return response.get('transitions', [])
        except Exception as e:
            logger.error(f"Error getting transitions for {issue_key}: {e}")
            raise

    async def create_issue(self, project_key: str, summary: str, description: str, 
                          issue_type: str, assignee: Optional[str] = None, 
                          priority: Optional[str] = None, labels: Optional[List[str]] = None,
                          custom_fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Create a new issue in JIRA.

        Args:
            project_key: Key of the project to create issue in
            summary: Issue summary
            description: Issue description
            issue_type: Type of the issue to create
            assignee: Name of the assignee (optional)
            priority: Name of the priority (optional)
            labels: List of labels to add to the issue (optional)
            custom_fields: Dictionary of custom fields to set (optional)

        Returns:
            Dictionary with created issue information (key, id, self)
        """
        fields = {
            'project': {'key': project_key},
            'summary': summary,
            'description': description,
            'issuetype': {'name': issue_type}
        }
        
        if assignee:
            fields['assignee'] = {'name': assignee}
        
        if priority:
            fields['priority'] = {'name': priority}
        
        if labels:
            fields['labels'] = labels
        
        if custom_fields:
            fields.update(custom_fields)
        
        payload = {'fields': fields}
        
        return await self._make_request('POST', '/rest/api/2/issue', json=payload)

    async def get_project(self, project_key: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific project.

        Args:
            project_key: The project key (e.g., PROJECT)

        Returns:
            Detailed project information
        """
        endpoint = f'/rest/api/2/project/{project_key}'
        return await self._make_request('GET', endpoint)

    async def get_create_meta(self, project_keys: Optional[List[str]] = None,
                             issue_type_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Get metadata required for creating issues in Jira.

        Args:
            project_keys: List of project keys
            issue_type_names: List of issue type names

        Returns:
            Metadata for issue creation
        """
        params = {}
        if project_keys:
            params['projectKeys'] = ','.join(project_keys)
        if issue_type_names:
            params['issuetypeNames'] = ','.join(issue_type_names)
        
        return await self._make_request('GET', '/rest/api/2/issue/createmeta', params=params)

    async def close(self):
        """Close the HTTP session"""
        if self.session:
            await self.session.close()
            logger.info("JIRA client session closed")

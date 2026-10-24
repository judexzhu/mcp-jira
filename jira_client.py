"""
Async JIRA client module for the MCP server.
Handles async interactions with the JIRA API using aiohttp.
"""
import os
import asyncio
from typing import Dict, List, Optional, Any, Protocol, runtime_checkable
import aiohttp
from asyncio_throttle import Throttler
import logging

logger = logging.getLogger(__name__)

def _adf_to_text(node: Any) -> str:
    """Convert Atlassian Document Format (ADF) to plain text.
    
    ADF is the rich-text JSON format used by Jira Cloud v3 API.
    Falls through gracefully if node is already a string.
    """
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if node.get('type') == 'text':
            return node.get('text', '')
        if node.get('type') == 'hardBreak':
            return '\n'
        if node.get('type') == 'mention':
            return node.get('attrs', {}).get('text', '')
        if node.get('type') == 'emoji':
            return node.get('attrs', {}).get('shortName', '')
        if node.get('type') == 'inlineCard':
            return node.get('attrs', {}).get('url', '')
        content = node.get('content', [])
        texts = [_adf_to_text(child) for child in content]
        block_types = ('paragraph', 'heading', 'bulletList', 'orderedList',
                       'listItem', 'blockquote', 'codeBlock', 'table',
                       'tableRow', 'tableCell', 'tableHeader', 'rule',
                       'mediaSingle', 'decisionList', 'taskList')
        if node.get('type') in block_types:
            return ''.join(t for t in texts if t).rstrip() + '\n'
        return ''.join(texts)
    if isinstance(node, list):
        return ''.join(_adf_to_text(item) for item in node)
    return ''

def _text_to_adf(text: str) -> Dict[str, Any]:
    """Convert plain text to Atlassian Document Format (ADF).

    Produces a minimal valid ADF document. For richer formatting,
    callers should construct ADF directly.
    """
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": text}]}
        ]
    }

def _transform_issue(issue: Dict[str, Any]) -> Dict[str, Any]:
    """Transform JIRA issue to optimized format (40-50% token reduction)."""
    fields = issue.get('fields', {})

    result = {
        'key': issue['key'],
        'summary': fields.get('summary'),
    }

    # Extract simple values from nested objects
    if status := fields.get('status'):
        result['status'] = status.get('name')

    if assignee := fields.get('assignee'):
        result['assignee'] = assignee.get('displayName')

    if priority := fields.get('priority'):
        result['priority'] = priority.get('name')

    if issue_type := fields.get('issuetype'):
        result['type'] = issue_type.get('name')

    # Include timestamps
    if created := fields.get('created'):
        result['created'] = created

    if updated := fields.get('updated'):
        result['updated'] = updated

    # Conditional fields (only if present and non-empty)
    if desc := fields.get('description'):
        result['desc'] = _adf_to_text(desc).strip() if isinstance(desc, dict) else desc

    if labels := fields.get('labels'):
        if labels:  # Only if non-empty array
            result['labels'] = labels

    return result

def _transform_comment(comment: Dict[str, Any]) -> Dict[str, Any]:
    """Transform JIRA comment to optimized format (60% token reduction)."""
    body = comment.get('body')
    if isinstance(body, dict):
        body = _adf_to_text(body).strip()
    result = {
        'author': comment.get('author', {}).get('displayName'),
        'body': body,
        'created': comment.get('created'),
    }

    # Only include updated if different from created
    updated = comment.get('updated')
    created = comment.get('created')
    if updated and updated != created:
        result['updated'] = updated

    return result

def _transform_link(linked_issue: Dict[str, Any]) -> Dict[str, Any]:
    """Transform JIRA issue link to optimized format (50% token reduction)."""
    return {
        'key': linked_issue.get('key'),
        'summary': linked_issue.get('fields', {}).get('summary'),
        'status': linked_issue.get('fields', {}).get('status', {}).get('name'),
    }

def _transform_transition(transition: Dict[str, Any]) -> Dict[str, Any]:
    """Transform JIRA transition to optimized format (50% token reduction)."""
    return {
        'id': transition.get('id'),
        'name': transition.get('name'),
        'to': transition.get('to', {}).get('name'),
    }

def _transform_field(field: Dict[str, Any]) -> Dict[str, Any]:
    """Transform JIRA field definition to optimized format."""
    return {
        'id': field.get('id'),
        'name': field.get('name'),
        'custom': field.get('custom', False),
        'type': (field.get('schema') or {}).get('type'),
    }

def _transform_myself(user: Dict[str, Any]) -> Dict[str, Any]:
    """Transform the /myself payload, which names the user differently on Cloud and Server."""
    return {
        'id': user.get('accountId') or user.get('name') or user.get('key'),
        'display_name': user.get('displayName'),
        'email': user.get('emailAddress'),
        'active': user.get('active'),
    }

class JiraHttpError(Exception):
    """HTTP error from the JIRA API, keeping the status and body for callers."""

    def __init__(self, status: int, reason: str, url: str, body: str):
        self.status = status
        self.reason = reason
        self.url = url
        self.body = body
        super().__init__(
            f"JIRA API request failed: {status}, message='{reason}', url='{url}', response='{body[:200]}'"
        )

@runtime_checkable
class JiraClientProtocol(Protocol):
    """Seam definition for JIRA client. Both AsyncJiraClient and test fakes implement this."""
    async def search_issues(self, jql: str, max_results: int = 50, start_at: int = 0) -> Dict[str, Any]: ...
    async def get_issue(self, issue_key: str, include_subtasks: bool = False, include_transitions: bool = False) -> Dict[str, Any]: ...
    async def create_issue(self, project_key: str, summary: str, description: str, issue_type: str, assignee: Optional[str] = None, priority: Optional[str] = None, labels: Optional[List[str]] = None, custom_fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]: ...
    async def update_issue(self, issue_key: str, summary: Optional[str] = None, description: Optional[str] = None, assignee: Optional[str] = None, priority: Optional[str] = None, labels: Optional[List[str]] = None, comment: Optional[str] = None, custom_fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]: ...
    async def transition_issue(self, issue_key: str, transition_id: str, comment: Optional[str] = None) -> Dict[str, Any]: ...
    async def get_create_meta(self, project_key: str, issue_type: Optional[str] = None) -> Dict[str, Any]: ...
    async def close(self) -> None: ...


class _CloudFormat:
    """Cloud-specific formatting: ADF bodies, accountId assignee, v3 endpoints."""
    api_prefix = "/rest/api/3"
    search_endpoint = "/rest/api/3/search/jql"

    @staticmethod
    def description(text: str) -> Any:
        return _text_to_adf(text)

    @staticmethod
    def assignee(value: str) -> Dict[str, str]:
        return {'accountId': value}

    @staticmethod
    def comment_body(text: str) -> Any:
        return _text_to_adf(text)


class _ServerFormat:
    """Server/DC formatting: plain text bodies, name assignee, v2 endpoints."""
    api_prefix = "/rest/api/2"
    search_endpoint = "/rest/api/2/search"

    @staticmethod
    def description(text: str) -> str:
        return text

    @staticmethod
    def assignee(value: str) -> Dict[str, str]:
        return {'name': value}

    @staticmethod
    def comment_body(text: str) -> str:
        return text


class AsyncJiraClient:
    """
    Async client for interacting with JIRA API.
    Handles authentication and provides async methods for working with JIRA issues.
    """

    def __init__(self, server_url: str, api_token: str, max_concurrent_requests: int = 2,
                 user_email: Optional[str] = None, session: Optional[aiohttp.ClientSession] = None):
        self.server_url = server_url.rstrip('/')
        self.api_token = api_token
        self.user_email = user_email
        self.max_concurrent_requests = max_concurrent_requests
        self.is_cloud = user_email is not None
        self._fmt = _CloudFormat() if self.is_cloud else _ServerFormat()
        self.throttler = Throttler(rate_limit=max_concurrent_requests, period=1.0)

        if session is not None:
            self.session = session
        else:
            connector = aiohttp.TCPConnector(
                limit=20, limit_per_host=10, ttl_dns_cache=300, use_dns_cache=True,
            )
            request_timeout = int(os.getenv('REQUEST_TIMEOUT', '30'))
            connect_timeout = int(os.getenv('CONNECT_TIMEOUT', '10'))
            timeout = aiohttp.ClientTimeout(total=request_timeout, connect=connect_timeout)
            session_kwargs: Dict[str, Any] = {
                "connector": connector, "timeout": timeout,
                "headers": {"Content-Type": "application/json", "Accept": "application/json"},
            }
            if user_email:
                session_kwargs["auth"] = aiohttp.BasicAuth(user_email, api_token)
            else:
                session_kwargs["headers"]["Authorization"] = f"Bearer {api_token}"
            self.session = aiohttp.ClientSession(**session_kwargs)

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
                            raise JiraHttpError(response.status, response.reason, url, error_text)
                        
                        # Log rate limit headers for monitoring
                        remaining = response.headers.get('X-RateLimit-Remaining')
                        limit = response.headers.get('X-RateLimit-Limit')
                        if remaining and limit:
                            logger.debug(f"Rate limit: {remaining}/{limit} remaining")
                        
                        if response.status == 204:
                            return {}
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

    async def search_issues(self, jql: str, max_results: int = 50,
                            start_at: int = 0) -> Dict[str, Any]:
        """
        Search for issues using JQL (JIRA Query Language).

        Args:
            jql: JQL query string
            max_results: Maximum number of results to return
            start_at: Index of the first result to return (for pagination)

        Returns:
            Dict with issues, total, start_at, max_results
        """
        search_fields = 'summary,status,assignee,priority,issuetype,created,updated,description,labels'

        params = {
            'jql': jql,
            'maxResults': max_results,
            'startAt': start_at,
            'fields': search_fields,
        }

        endpoint = self._fmt.search_endpoint

        response = await self._make_request('GET', endpoint, params=params)

        issues = response.get('issues', [])
        return {
            'issues': [_transform_issue(issue) for issue in issues],
            'total': response.get('total', len(issues)),
            'start_at': start_at,
            'max_results': max_results,
        }

    async def get_issue(self, issue_key: str, include_subtasks: bool = False,
                       include_transitions: bool = False) -> Dict[str, Any]:
        """
        Get detailed information about a specific issue.

        Args:
            issue_key: The issue key (e.g., PROJECT-123)
            include_subtasks: Fetch subtasks (extra API call)
            include_transitions: Fetch available transitions (extra API call)

        Returns:
            Detailed issue information (optimized format)
        """
        endpoint = f'{self._fmt.api_prefix}/issue/{issue_key}'
        params = {
            'fields': 'summary,status,assignee,priority,issuetype,created,updated,description,comment,issuelinks,labels'
        }

        issue = await self._make_request('GET', endpoint, params=params)
        result = _transform_issue(issue)

        comments = issue.get('fields', {}).get('comment', {}).get('comments', [])
        if comments:
            result['comments'] = [_transform_comment(c) for c in comments]

        issue_links = issue.get('fields', {}).get('issuelinks', [])
        if issue_links:
            links_by_type = {}
            for link in issue_links:
                link_type = link.get('type', {}).get('name', 'Unknown')

                if link_type not in links_by_type:
                    links_by_type[link_type] = []

                if 'outwardIssue' in link:
                    linked_issue = link['outwardIssue']
                elif 'inwardIssue' in link:
                    linked_issue = link['inwardIssue']
                else:
                    continue

                links_by_type[link_type].append(_transform_link(linked_issue))

            if links_by_type:
                result['links'] = links_by_type

        if include_subtasks:
            st_endpoint = f'{self._fmt.api_prefix}/issue/{issue_key}'
            st_issue = await self._make_request('GET', st_endpoint, params={'fields': 'subtasks'})
            subtasks = st_issue.get('fields', {}).get('subtasks', [])
            if subtasks:
                result['subtasks'] = [_transform_issue(st) for st in subtasks]

        if include_transitions:
            tr_endpoint = f'{self._fmt.api_prefix}/issue/{issue_key}/transitions'
            tr_response = await self._make_request('GET', tr_endpoint)
            transitions = tr_response.get('transitions', [])
            if transitions:
                result['transitions'] = [_transform_transition(t) for t in transitions]

        return result

    async def update_issue(self, issue_key: str, summary: Optional[str] = None,
                           description: Optional[str] = None, assignee: Optional[str] = None,
                           priority: Optional[str] = None, labels: Optional[List[str]] = None,
                           comment: Optional[str] = None,
                           custom_fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Update fields on an existing issue, optionally adding a comment.
        Handles Cloud/Server formatting internally (ADF, accountId).

        Args:
            issue_key: The issue key (e.g., PROJECT-123)
            summary: New summary
            description: New description (converted to ADF on Cloud)
            assignee: New assignee (accountId on Cloud, username on Server/DC)
            priority: New priority name
            labels: New labels list (replaces existing)
            comment: Optional comment to add after update
            custom_fields: Dictionary of custom fields to update

        Returns:
            Confirmation dict with issue key
        """
        fields = {}
        if summary is not None:
            fields['summary'] = summary
        if description is not None:
            fields['description'] = self._fmt.description(description)
        if assignee is not None:
            fields['assignee'] = self._fmt.assignee(assignee)
        if priority is not None:
            fields['priority'] = {'name': priority}
        if labels is not None:
            fields['labels'] = labels
        if custom_fields:
            fields.update(custom_fields)

        if fields:
            endpoint = f'{self._fmt.api_prefix}/issue/{issue_key}'
            await self._make_request('PUT', endpoint, json={'fields': fields})

        if comment:
            await self.add_comment(issue_key, comment)

        return {'key': issue_key, 'updated': True}

    async def transition_issue(self, issue_key: str, transition_id: str,
                               comment: Optional[str] = None) -> Dict[str, Any]:
        """
        Transition an issue to a new workflow state.

        Args:
            issue_key: The issue key (e.g., PROJECT-123)
            transition_id: ID of the transition (from get_issue with include_transitions=True)
            comment: Optional comment to add with the transition

        Returns:
            Confirmation dict with issue key and target status
        """
        endpoint = f'{self._fmt.api_prefix}/issue/{issue_key}/transitions'
        payload = {'transition': {'id': transition_id}}

        if comment:
            payload['update'] = {'comment': [{'add': {'body': self._fmt.comment_body(comment)}}]}

        await self._make_request('POST', endpoint, json=payload)

        return {'key': issue_key, 'transitioned': True, 'transition_id': transition_id}

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
            Dictionary with created issue key (optimized format)
        """
        fields = {
            'project': {'key': project_key},
            'summary': summary,
            'description': self._fmt.description(description),
            'issuetype': {'name': issue_type}
        }

        if assignee:
            fields['assignee'] = self._fmt.assignee(assignee)

        if priority:
            fields['priority'] = {'name': priority}

        if labels:
            fields['labels'] = labels

        if custom_fields:
            fields.update(custom_fields)

        payload = {'fields': fields}

        endpoint = f'{self._fmt.api_prefix}/issue'
        response = await self._make_request('POST', endpoint, json=payload)
        return {'key': response.get('key')}

    async def add_comment(self, issue_key: str, body: str) -> Dict[str, Any]:
        """
        Add a comment to a specific issue.

        Args:
            issue_key: The issue key (e.g., PROJECT-123)
            body: The comment text

        Returns:
            Dictionary with comment id and body
        """
        endpoint = f'{self._fmt.api_prefix}/issue/{issue_key}/comment'
        payload = {'body': self._fmt.comment_body(body)}
        response = await self._make_request('POST', endpoint, json=payload)
        return _transform_comment(response)

    async def get_project(self, project_key: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific project.

        Args:
            project_key: The project key (e.g., PROJECT)

        Returns:
            Detailed project information
        """
        endpoint = f'{self._fmt.api_prefix}/project/{project_key}'
        return await self._make_request('GET', endpoint)

    async def get_comments(self, issue_key: str, max_results: int = 50,
                           start_at: int = 0) -> Dict[str, Any]:
        """
        Get comments on an issue, one page at a time.

        Args:
            issue_key: The issue key (e.g., PROJECT-123)
            max_results: Maximum number of comments to return
            start_at: Index of the first comment to return (for pagination)

        Returns:
            Dict with comments, total, start_at, max_results
        """
        endpoint = f'{self._fmt.api_prefix}/issue/{issue_key}/comment'
        params = {'maxResults': max_results, 'startAt': start_at}
        response = await self._make_request('GET', endpoint, params=params)

        comments = response.get('comments', [])
        return {
            'comments': [_transform_comment(c) for c in comments],
            'total': response.get('total', len(comments)),
            'start_at': start_at,
            'max_results': max_results,
        }

    async def get_fields(self) -> Dict[str, Any]:
        """
        List the fields defined on this JIRA instance.

        Returns:
            Dict with fields in optimized format
        """
        fields = await self._make_request('GET', f'{self._fmt.api_prefix}/field')
        return {'fields': [_transform_field(f) for f in fields]}

    async def get_myself(self) -> Dict[str, Any]:
        """
        Get the user the client authenticates as.

        Returns:
            User identity in optimized format
        """
        user = await self._make_request('GET', f'{self._fmt.api_prefix}/myself')
        return _transform_myself(user)

    async def get_create_meta(self, project_key: str,
                             issue_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Get metadata required for creating issues — issue types and their fields.

        If issue_type is provided, returns fields for that type (transformed).
        Otherwise, returns available issue types for the project.

        Args:
            project_key: Project key (e.g., "OCPBUGS")
            issue_type: Issue type name (e.g., "Bug"). If omitted, lists available types.

        Returns:
            Transformed metadata — issue types list, or field requirements for one type
        """
        if issue_type is None:
            response = await self._make_request(
                'GET', f'{self._fmt.api_prefix}/issue/createmeta',
                params={'projectKeys': project_key}
            )
            projects = response.get('projects', [])
            if not projects:
                return {'project': project_key, 'issue_types': []}
            types = projects[0].get('issuetypes', [])
            return {
                'project': project_key,
                'issue_types': [{'id': t['id'], 'name': t['name'], 'subtask': t.get('subtask', False)} for t in types]
            }

        # Get issue types to find the ID for the given name
        meta = await self.get_create_meta(project_key)
        type_match = next((t for t in meta['issue_types'] if t['name'].lower() == issue_type.lower()), None)
        if not type_match:
            available = [t['name'] for t in meta['issue_types']]
            raise ValueError(f"Issue type '{issue_type}' not found in {project_key}. Available: {available}")

        # Fetch fields for this issue type
        response = await self._make_request(
            'GET', f'{self._fmt.api_prefix}/issue/createmeta/{project_key}/issuetypes/{type_match["id"]}'
        )

        fields = []
        for f in response.get('fields', []):
            field = {
                'key': f.get('fieldId') or f.get('key'),
                'name': f.get('name'),
                'required': f.get('required', False),
            }
            allowed = f.get('allowedValues')
            if allowed:
                field['allowed'] = [v.get('name') or v.get('value') for v in allowed[:50]]
            fields.append(field)

        return {
            'project': project_key,
            'issue_type': issue_type,
            'fields': sorted(fields, key=lambda x: (not x['required'], x['name'])),
        }

    async def close(self):
        """Close the HTTP session"""
        if self.session:
            await self.session.close()
            logger.info("JIRA client session closed")

"""JIRA operations shared by the MCP server and the CLI.

Both entry points call these functions and neither builds a client of its own,
so a CLI command and its MCP tool are provably the same code path. The client is
created lazily inside the running event loop, because aiohttp needs one to open
its session, and is process-global afterwards.
"""

import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from .client import AsyncJiraClient

load_dotenv()

_client: Optional[AsyncJiraClient] = None


def _set_client(client: Optional[AsyncJiraClient]) -> None:
    """Override the client instance (for testing)."""
    global _client
    _client = client


async def get_client() -> AsyncJiraClient:
    """Get or create the shared JIRA client from the environment."""
    global _client

    if _client is None:
        server_url = os.getenv("JIRA_SERVER_URL")
        api_token = os.getenv("JIRA_API_TOKEN")
        user_email = os.getenv("JIRA_USER_EMAIL")

        missing = [
            name
            for name, value in (
                ("JIRA_SERVER_URL", server_url),
                ("JIRA_API_TOKEN", api_token),
                ("JIRA_USER_EMAIL", user_email),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"missing required environment: {', '.join(missing)}")

        _client = AsyncJiraClient(
            server_url,
            api_token,
            user_email,
            int(os.getenv("MAX_CONCURRENT_REQUESTS", "2")),
        )

    return _client


async def close_client() -> None:
    """Close the shared client, if one was created."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def search_issues(jql: str, max_results: int = 50,
                        start_at: int = 0) -> Dict[str, Any]:
    """
    Search for JIRA issues using JQL (JIRA Query Language).

    Returns a paginated result with total count. Use start_at to page through large result sets.

    Args:
        jql: JQL query string (e.g., "project = PROJECT AND status = 'In Progress'")
        max_results: Maximum number of results to return (default: 50)
        start_at: Index of the first result (default: 0, for pagination)

    Returns:
        Dict with issues array, total count, start_at, and max_results
    """
    client = await get_client()
    return await client.search_issues(jql, max_results, start_at)


async def get_issue(issue_key: str, include_subtasks: bool = False,
                    include_transitions: bool = False) -> Dict[str, Any]:
    """
    Get detailed information about a specific JIRA issue including comments and links.
    Optionally include subtasks and available workflow transitions.

    Args:
        issue_key: The JIRA issue key (e.g., "PROJECT-123")
        include_subtasks: Also fetch subtasks (extra API call)
        include_transitions: Also fetch available workflow transitions (extra API call)

    Returns:
        Issue details with comments, links, and optionally subtasks/transitions
    """
    client = await get_client()
    return await client.get_issue(issue_key, include_subtasks, include_transitions)


async def create_issue(project_key: str, summary: str, description: str,
                       issue_type_name: str, assignee_name: Optional[str] = None,
                       priority_name: Optional[str] = None,
                       labels: Optional[List[str]] = None,
                       custom_fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Creates a new issue in a specified Jira project. Requires project key, summary, description, and issue type.
    Optional fields include assignee, priority, labels, and custom fields.

    Pass an accountId string for assignee_name (not a username).

    Args:
        project_key: Key of the project to create issue in (e.g., "PROJECT")
        summary: Issue summary
        description: Issue description
        issue_type_name: Type of the issue to create (e.g., "Bug", "Task")
        assignee_name: Assignee accountId (optional)
        priority_name: Name of the priority (optional)
        labels: List of labels to add to the issue (optional)
        custom_fields: Dictionary of custom fields to set (optional)

    Returns:
        JSON object with the key of the new issue
    """
    client = await get_client()
    return await client.create_issue(
        project_key, summary, description, issue_type_name,
        assignee_name, priority_name, labels, custom_fields
    )


async def update_issue(issue_key: str, summary: Optional[str] = None,
                       description: Optional[str] = None,
                       assignee: Optional[str] = None,
                       priority: Optional[str] = None,
                       labels: Optional[List[str]] = None,
                       comment: Optional[str] = None,
                       custom_fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Update fields on an existing JIRA issue. All field parameters are optional — only provided
    fields are updated. Optionally add a comment in the same call.

    Pass an accountId string for assignee (not a username).

    Args:
        issue_key: The JIRA issue key (e.g., "PROJECT-123")
        summary: New summary (optional)
        description: New description (optional)
        assignee: New assignee accountId (optional)
        priority: New priority name (optional)
        labels: New labels list — replaces existing labels (optional)
        comment: Comment to add after update (optional)
        custom_fields: Dictionary of custom fields to update (optional)

    Returns:
        Confirmation with issue key
    """
    client = await get_client()
    return await client.update_issue(
        issue_key, summary=summary, description=description,
        assignee=assignee, priority=priority, labels=labels,
        comment=comment, custom_fields=custom_fields
    )


async def transition_issue(issue_key: str, transition_id: str,
                           comment: Optional[str] = None) -> Dict[str, Any]:
    """
    Transition a JIRA issue to a new workflow state. Use get_issue with
    include_transitions=True to see available transitions and their IDs.

    Args:
        issue_key: The JIRA issue key (e.g., "PROJECT-123")
        transition_id: ID of the transition to execute (from get_issue transitions)
        comment: Optional comment to add with the transition

    Returns:
        Confirmation with issue key
    """
    client = await get_client()
    return await client.transition_issue(issue_key, transition_id, comment)


async def get_create_meta(project_key: str,
                          issue_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Get metadata for creating issues — available issue types and their required/optional fields.

    Call without issue_type to list available types. Call with issue_type to get field requirements.

    Args:
        project_key: Project key (e.g., "OCPBUGS")
        issue_type: Issue type name (e.g., "Bug"). If omitted, lists available types.

    Returns:
        Issue types list, or field details (name, required, allowed values) for one type
    """
    client = await get_client()
    return await client.get_create_meta(project_key, issue_type)


async def add_comment(issue_key: str, body: str) -> Dict[str, Any]:
    """
    Add a comment to an issue.

    Args:
        issue_key: The JIRA issue key (e.g., "PROJECT-123")
        body: The comment text

    Returns:
        The created comment
    """
    client = await get_client()
    return await client.add_comment(issue_key, body)


async def get_comments(issue_key: str, max_results: int = 50,
                       start_at: int = 0) -> Dict[str, Any]:
    """
    List an issue's comments, one page at a time.

    Args:
        issue_key: The JIRA issue key (e.g., "PROJECT-123")
        max_results: Maximum number of comments to return (default: 50)
        start_at: Index of the first comment (default: 0, for pagination)

    Returns:
        Dict with comments array, total count, start_at, and max_results
    """
    client = await get_client()
    return await client.get_comments(issue_key, max_results, start_at)


async def get_project(project_key: str) -> Dict[str, Any]:
    """
    Get detailed information about a project.

    Args:
        project_key: The project key (e.g., "PROJECT")

    Returns:
        Project details
    """
    client = await get_client()
    return await client.get_project(project_key)


async def get_fields() -> Dict[str, Any]:
    """
    List the fields defined on the instance, with their ids and types.

    Returns:
        Dict with a fields array
    """
    client = await get_client()
    return await client.get_fields()


async def get_myself() -> Dict[str, Any]:
    """
    Get the user the API token authenticates as.

    Returns:
        User identity
    """
    client = await get_client()
    return await client.get_myself()

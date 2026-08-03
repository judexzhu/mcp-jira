#!/usr/bin/env python3
"""
JIRA MCP Server - Async Implementation
A high-performance Model Context Protocol server for JIRA integration.
"""
import logging
import os
import sys
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

from mcp.server.fastmcp import FastMCP
from jira_client import AsyncJiraClient

load_dotenv()


def setup_logging():
    """Set up logging configuration."""
    log_level = os.getenv('LOG_LEVEL', 'ERROR').upper()

    handlers = [logging.FileHandler('jira_mcp_server.log', mode='a')]

    if os.getenv('LOG_TO_STDOUT', 'false').lower() == 'true':
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )

    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)

    return logging.getLogger(__name__)


logger = setup_logging()

mcp = FastMCP("JIRA MCP Server")

_jira_client: Optional[AsyncJiraClient] = None


def _set_client(client):
    """Override the JIRA client instance (for testing)."""
    global _jira_client
    _jira_client = client


async def get_jira_client() -> AsyncJiraClient:
    """Get or create the JIRA client instance."""
    global _jira_client

    if _jira_client is None:
        server_url = os.getenv("JIRA_SERVER_URL")
        api_token = os.getenv("JIRA_API_TOKEN")
        user_email = os.getenv("JIRA_USER_EMAIL")
        max_concurrent = int(os.getenv("MAX_CONCURRENT_REQUESTS", "2"))

        if not server_url or not api_token:
            raise ValueError("JIRA_SERVER_URL and JIRA_API_TOKEN must be set")

        _jira_client = AsyncJiraClient(server_url, api_token, max_concurrent, user_email=user_email)
        logger.info(f"Initialized JIRA client for {server_url}")

    return _jira_client


# MCP Tools

@mcp.tool()
async def jira_search_issues(jql: str, max_results: int = 50,
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
    client = await get_jira_client()
    return await client.search_issues(jql, max_results, start_at)


@mcp.tool()
async def jira_get_issue(
    issue_key: str,
    include_subtasks: bool = False,
    include_transitions: bool = False,
) -> Dict[str, Any]:
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
    client = await get_jira_client()
    return await client.get_issue(issue_key, include_subtasks, include_transitions)


@mcp.tool()
async def jira_create_issue(
    project_key: str,
    summary: str,
    description: str,
    issue_type_name: str,
    assignee_name: Optional[str] = None,
    priority_name: Optional[str] = None,
    labels: Optional[List[str]] = None,
    custom_fields: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Creates a new issue in a specified Jira project. Requires project key, summary, description, and issue type.
    Optional fields include assignee, priority, labels, and custom fields.

    On Cloud instances, pass an accountId string for assignee_name (not a username).

    Args:
        project_key: Key of the project to create issue in (e.g., "PROJECT")
        summary: Issue summary
        description: Issue description
        issue_type_name: Type of the issue to create (e.g., "Bug", "Task")
        assignee_name: Assignee — accountId on Cloud, username on Server/DC (optional)
        priority_name: Name of the priority (optional)
        labels: List of labels to add to the issue (optional)
        custom_fields: Dictionary of custom fields to set (optional)

    Returns:
        JSON object with the key of the new issue
    """
    client = await get_jira_client()
    return await client.create_issue(
        project_key, summary, description, issue_type_name,
        assignee_name, priority_name, labels, custom_fields
    )


@mcp.tool()
async def jira_update_issue(
    issue_key: str,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    assignee: Optional[str] = None,
    priority: Optional[str] = None,
    labels: Optional[List[str]] = None,
    comment: Optional[str] = None,
    custom_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Update fields on an existing JIRA issue. All field parameters are optional — only provided
    fields are updated. Optionally add a comment in the same call.

    On Cloud instances, pass an accountId string for assignee (not a username).

    Args:
        issue_key: The JIRA issue key (e.g., "PROJECT-123")
        summary: New summary (optional)
        description: New description (optional)
        assignee: New assignee — accountId on Cloud, username on Server/DC (optional)
        priority: New priority name (optional)
        labels: New labels list — replaces existing labels (optional)
        comment: Comment to add after update (optional)
        custom_fields: Dictionary of custom fields to update (optional)

    Returns:
        Confirmation with issue key
    """
    client = await get_jira_client()
    return await client.update_issue(
        issue_key, summary=summary, description=description,
        assignee=assignee, priority=priority, labels=labels,
        comment=comment, custom_fields=custom_fields
    )


@mcp.tool()
async def jira_transition_issue(
    issue_key: str,
    transition_id: str,
    comment: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Transition a JIRA issue to a new workflow state. Use jira_get_issue with
    include_transitions=True to see available transitions and their IDs.

    Args:
        issue_key: The JIRA issue key (e.g., "PROJECT-123")
        transition_id: ID of the transition to execute (from jira_get_issue transitions)
        comment: Optional comment to add with the transition

    Returns:
        Confirmation with issue key
    """
    client = await get_jira_client()
    return await client.transition_issue(issue_key, transition_id, comment)


@mcp.tool()
async def jira_get_create_meta(
    project_key: str,
    issue_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get metadata for creating issues — available issue types and their required/optional fields.

    Call without issue_type to list available types. Call with issue_type to get field requirements.

    Args:
        project_key: Project key (e.g., "OCPBUGS")
        issue_type: Issue type name (e.g., "Bug"). If omitted, lists available types.

    Returns:
        Issue types list, or field details (name, required, allowed values) for one type
    """
    client = await get_jira_client()
    return await client.get_create_meta(project_key, issue_type)


# MCP Prompts

@mcp.prompt()
def my_open_issues() -> list:
    """Get all open issues assigned to you."""
    return [{"role": "user", "content": {
        "type": "text",
        "text": "Search JIRA for my open issues using: assignee = currentUser() AND resolution = Unresolved ORDER BY updated DESC"
    }}]


@mcp.prompt()
def my_watched_issues(days: int = 7) -> list:
    """Get recent updates on issues you're watching."""
    return [{"role": "user", "content": {
        "type": "text",
        "text": f"Search JIRA for issues I'm watching that were updated recently using: watcher = currentUser() AND updated >= -{days}d ORDER BY updated DESC"
    }}]


def main():
    """Validate environment and run the MCP server."""
    required_vars = ["JIRA_SERVER_URL", "JIRA_API_TOKEN"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please set these in your .env file")
        sys.exit(1)

    logger.info("Starting JIRA MCP Server (Async)")
    logger.info(f"JIRA Server: {os.getenv('JIRA_SERVER_URL')}")
    logger.info(f"Max Concurrent Requests: {os.getenv('MAX_CONCURRENT_REQUESTS', '2')}")

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

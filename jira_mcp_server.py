#!/usr/bin/env python3
"""
JIRA MCP Server - Async Implementation
A high-performance Model Context Protocol server for JIRA integration.
"""
import asyncio
import logging
import os
import sys
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

from mcp.server.fastmcp import FastMCP
from jira_client import AsyncJiraClient

# Load environment variables
load_dotenv()

# Configure logging
def setup_logging():
    """Set up logging configuration."""
    log_level = os.getenv('LOG_LEVEL', 'ERROR').upper()
    
    # For MCP stdio transport, only log to file to avoid interfering with JSON protocol
    handlers = [logging.FileHandler('jira_mcp_server.log', mode='a')]
    
    # Only add stdout logging if explicitly requested (for debugging)
    if os.getenv('LOG_TO_STDOUT', 'false').lower() == 'true':
        handlers.append(logging.StreamHandler(sys.stdout))
    
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
    
    # Set specific loggers to reduce noise
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)

logger = setup_logging()

# Validate environment variables on startup
required_vars = ["JIRA_SERVER_URL", "JIRA_API_TOKEN"]
missing_vars = [var for var in required_vars if not os.getenv(var)]

if missing_vars:
    logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    logger.error("Please set these in your .env file")
    sys.exit(1)

# Log configuration (only to file to avoid interfering with MCP stdio)
logger.info("Starting JIRA MCP Server (Async)")
logger.info(f"JIRA Server: {os.getenv('JIRA_SERVER_URL')}")
logger.info(f"Max Concurrent Requests: {os.getenv('MAX_CONCURRENT_REQUESTS', '2')}")
logger.info(f"Log Level: {os.getenv('LOG_LEVEL', 'ERROR')}")
logger.info(f"Log to stdout: {os.getenv('LOG_TO_STDOUT', 'false')}")
logger.info(f"Request timeout: {os.getenv('REQUEST_TIMEOUT', '30')}s")
logger.info(f"Connect timeout: {os.getenv('CONNECT_TIMEOUT', '10')}s")

# Initialize the FastMCP server
mcp = FastMCP("JIRA MCP Server")

# Global client instance
jira_client: Optional[AsyncJiraClient] = None

async def get_jira_client() -> AsyncJiraClient:
    """Get or create the JIRA client instance."""
    global jira_client
    
    if jira_client is None:
        server_url = os.getenv("JIRA_SERVER_URL")
        api_token = os.getenv("JIRA_API_TOKEN")
        max_concurrent = int(os.getenv("MAX_CONCURRENT_REQUESTS", "2"))
        
        if not server_url or not api_token:
            raise ValueError("JIRA_SERVER_URL and JIRA_API_TOKEN must be set in environment variables")
        
        jira_client = AsyncJiraClient(server_url, api_token, max_concurrent)
        logger.info(f"Initialized JIRA client for {server_url} with max_concurrent={max_concurrent}")
    
    return jira_client

# MCP Tools
@mcp.tool()
async def jira_search_issues(jql: str, max_results: int = 50) -> List[Dict[str, Any]]:
    """
    Search for JIRA issues using JQL (JIRA Query Language).
    
    Args:
        jql: JQL query string (e.g., "project = PROJECT AND status = 'In Progress'")
        max_results: Maximum number of results to return (default: 50)
        
    Returns:
        List of issues matching the query
    """
    try:
        client = await get_jira_client()
        logger.info(f"Searching issues with JQL: {jql[:100]}...")
        results = await client.search_issues(jql, max_results)
        logger.info(f"Found {len(results)} issues")
        return results
    except Exception as e:
        logger.error(f"Error searching issues: {e}")
        raise

@mcp.tool()
async def jira_get_issue_details(issue_key: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific JIRA issue.
    
    Args:
        issue_key: The JIRA issue key (e.g., "PROJECT-123")
        
    Returns:
        Detailed information about the issue
    """
    try:
        client = await get_jira_client()
        logger.info(f"Getting details for issue: {issue_key}")
        result = await client.get_issue(issue_key)
        return result
    except Exception as e:
        logger.error(f"Error getting issue details for {issue_key}: {e}")
        raise

@mcp.tool()
async def jira_get_issue_comments(issue_key: str) -> List[Dict[str, Any]]:
    """
    Get all comments for a specific JIRA issue.
    
    Args:
        issue_key: The JIRA issue key (e.g., "PROJECT-123")
        
    Returns:
        List of comments for the issue
    """
    try:
        client = await get_jira_client()
        logger.info(f"Getting comments for issue: {issue_key}")
        results = await client.get_issue_comments(issue_key)
        logger.info(f"Found {len(results)} comments")
        return results
    except Exception as e:
        logger.error(f"Error getting comments for {issue_key}: {e}")
        raise

@mcp.tool()
async def jira_get_issue_links(issue_key: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get all links for a specific JIRA issue, categorized by link type.
    
    Args:
        issue_key: The JIRA issue key (e.g., "PROJECT-123")
        
    Returns:
        Dictionary of link types to lists of linked issues
    """
    try:
        client = await get_jira_client()
        logger.info(f"Getting links for issue: {issue_key}")
        results = await client.get_issue_links(issue_key)
        total_links = sum(len(links) for links in results.values())
        logger.info(f"Found {total_links} links across {len(results)} link types")
        return results
    except Exception as e:
        logger.error(f"Error getting links for {issue_key}: {e}")
        raise

@mcp.tool()
async def jira_get_epic_issues(epic_key: str) -> List[Dict[str, Any]]:
    """
    Get all issues that belong to a specific epic.
    
    Args:
        epic_key: The JIRA epic issue key (e.g., "PROJECT-123")
        
    Returns:
        List of issues in the epic
    """
    try:
        client = await get_jira_client()
        logger.info(f"Getting issues for epic: {epic_key}")
        results = await client.get_epic_issues(epic_key)
        logger.info(f"Found {len(results)} issues in epic")
        return results
    except Exception as e:
        logger.error(f"Error getting epic issues for {epic_key}: {e}")
        raise

@mcp.tool()
async def jira_get_subtasks(issue_key: str) -> List[Dict[str, Any]]:
    """
    Get all subtasks for a specific JIRA issue.
    
    Args:
        issue_key: The parent JIRA issue key (e.g., "PROJECT-123")
        
    Returns:
        List of subtasks for the issue
    """
    try:
        client = await get_jira_client()
        logger.info(f"Getting subtasks for issue: {issue_key}")
        results = await client.get_subtasks(issue_key)
        logger.info(f"Found {len(results)} subtasks")
        return results
    except Exception as e:
        logger.error(f"Error getting subtasks for {issue_key}: {e}")
        raise

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
    
    Args:
        project_key: Key of the project to create issue in (e.g., "PROJECT")
        summary: Issue summary
        description: Issue description
        issue_type_name: Type of the issue to create (e.g., "Bug", "Task")
        assignee_name: Name of the assignee (optional)
        priority_name: Name of the priority (optional)
        labels: List of labels to add to the issue (optional)
        custom_fields: Dictionary of custom fields to set (optional)
        
    Returns:
        JSON object with key, id, self of the new issue
    """
    try:
        client = await get_jira_client()
        logger.info(f"Creating issue in project {project_key}: {summary[:50]}...")
        result = await client.create_issue(
            project_key, summary, description, issue_type_name,
            assignee_name, priority_name, labels, custom_fields
        )
        logger.info(f"Created issue: {result.get('key', 'Unknown')}")
        return result
    except Exception as e:
        logger.error(f"Error creating issue: {e}")
        raise

@mcp.tool()
async def jira_get_available_transitions(issue_key: str) -> List[Dict[str, Any]]:
    """
    Lists the available workflow transitions for a given Jira issue, based on its current status and workflow configuration.
    
    Args:
        issue_key: The JIRA issue key (e.g., "PROJECT-123")
        
    Returns:
        List of transition objects (id, name, to status object)
    """
    try:
        client = await get_jira_client()
        logger.info(f"Getting available transitions for issue: {issue_key}")
        results = await client.get_available_transitions(issue_key)
        logger.info(f"Found {len(results)} available transitions")
        return results
    except Exception as e:
        logger.error(f"Error getting transitions for {issue_key}: {e}")
        raise

if __name__ == "__main__":
    mcp.run(transport="stdio")

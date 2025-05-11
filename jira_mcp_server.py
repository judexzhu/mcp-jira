"""
MCP Server for JIRA integration.
Provides tools for searching and retrieving information from JIRA.
"""
import os
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from mcp.server.fastmcp import FastMCP, Context
from jira_client import JiraClient

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("jira-mcp-server")

# Load environment variables
load_dotenv()

# Get JIRA credentials from environment variables
JIRA_SERVER_URL = os.getenv("JIRA_SERVER_URL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")


@dataclass
class AppContext:
    """Application context for the MCP server."""
    jira_client: JiraClient


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """
    Lifecycle manager for the MCP server.
    Sets up the JIRA client on startup.
    """
    # Check if JIRA credentials are set
    if not all([JIRA_SERVER_URL, JIRA_API_TOKEN, JIRA_EMAIL]):
        raise ValueError(
            "Missing JIRA credentials. Please set JIRA_SERVER_URL, JIRA_API_TOKEN, and JIRA_EMAIL environment variables."
        )
    
    # Initialize JIRA client
    logger.info(f"Connecting to JIRA server: {JIRA_SERVER_URL}")
    logger.debug(f"Using email: {JIRA_EMAIL}")
    logger.debug(f"API token length: {len(JIRA_API_TOKEN)}")
    
    try:
        # Test connection to JIRA
        jira_client = JiraClient(JIRA_SERVER_URL, JIRA_EMAIL, JIRA_API_TOKEN)
        # Try a simple operation to verify connection
        logger.debug("Testing JIRA connection by searching for a recent issue")
        test_result = jira_client.search_issues("created >= -1d", max_results=1)
        logger.debug(f"JIRA connection test successful: found {len(test_result)} issues")
        
        try:
            yield AppContext(jira_client=jira_client)
        finally:
            logger.info("Shutting down JIRA MCP server")
    except Exception as e:
        logger.error(f"Error connecting to JIRA: {str(e)}")
        logger.exception("Detailed exception information:")
        raise


# Create the MCP server
mcp = FastMCP(
    "JIRA MCP Server",
    description="MCP Server for interacting with JIRA",
    lifespan=app_lifespan,
    dependencies=["jira>=3.5.2", "python-dotenv>=1.0.0"]
)


# Define tools for searching and retrieving JIRA issues

@mcp.tool()
def search_issues(ctx: Context, jql: str, max_results: int = 50) -> Dict[str, Any]:
    """
    Search for JIRA issues using JQL (JIRA Query Language).
    
    Args:
        jql: JQL query string (e.g., "project = PROJECT AND status = 'In Progress'")
        max_results: Maximum number of results to return (default: 50)
        
    Returns:
        List of issues matching the query
    """
    jira_client = ctx.request_context.lifespan_context.jira_client
    try:
        issues = jira_client.search_issues(jql, max_results)
        return {"issues": issues, "count": len(issues)}
    except Exception as e:
        logger.error(f"Error searching issues: {str(e)}")
        return {"error": str(e), "issues": [], "count": 0}


@mcp.tool()
def get_issue_details(ctx: Context, issue_key: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific JIRA issue.
    
    Args:
        issue_key: The JIRA issue key (e.g., "PROJECT-123")
        
    Returns:
        Detailed information about the issue
    """
    jira_client = ctx.request_context.lifespan_context.jira_client
    try:
        issue = jira_client.get_issue(issue_key)
        return {"issue": issue}
    except Exception as e:
        logger.error(f"Error getting issue details: {str(e)}")
        return {"error": str(e), "issue": None}


@mcp.tool()
def get_issue_comments(ctx: Context, issue_key: str) -> Dict[str, Any]:
    """
    Get all comments for a specific JIRA issue.
    
    Args:
        issue_key: The JIRA issue key (e.g., "PROJECT-123")
        
    Returns:
        List of comments for the issue
    """
    jira_client = ctx.request_context.lifespan_context.jira_client
    try:
        comments = jira_client.get_issue_comments(issue_key)
        return {"comments": comments, "count": len(comments)}
    except Exception as e:
        logger.error(f"Error getting issue comments: {str(e)}")
        return {"error": str(e), "comments": [], "count": 0}


@mcp.tool()
def get_issue_links(ctx: Context, issue_key: str) -> Dict[str, Any]:
    """
    Get all links for a specific JIRA issue, categorized by link type.
    
    Args:
        issue_key: The JIRA issue key (e.g., "PROJECT-123")
        
    Returns:
        Dictionary of link types to lists of linked issues
    """
    jira_client = ctx.request_context.lifespan_context.jira_client
    try:
        links = jira_client.get_issue_links(issue_key)
        return {"links": links}
    except Exception as e:
        logger.error(f"Error getting issue links: {str(e)}")
        return {"error": str(e), "links": {}}


@mcp.tool()
def get_epic_issues(ctx: Context, epic_key: str) -> Dict[str, Any]:
    """
    Get all issues that belong to a specific epic.
    
    Args:
        epic_key: The JIRA epic issue key (e.g., "PROJECT-123")
        
    Returns:
        List of issues in the epic
    """
    jira_client = ctx.request_context.lifespan_context.jira_client
    try:
        issues = jira_client.get_epic_issues(epic_key)
        return {"issues": issues, "count": len(issues)}
    except Exception as e:
        logger.error(f"Error getting epic issues: {str(e)}")
        return {"error": str(e), "issues": [], "count": 0}


@mcp.tool()
def get_subtasks(ctx: Context, issue_key: str) -> Dict[str, Any]:
    """
    Get all subtasks for a specific JIRA issue.
    
    Args:
        issue_key: The parent JIRA issue key (e.g., "PROJECT-123")
        
    Returns:
        List of subtasks for the issue
    """
    jira_client = ctx.request_context.lifespan_context.jira_client
    try:
        subtasks = jira_client.get_subtasks(issue_key)
        return {"subtasks": subtasks, "count": len(subtasks)}
    except Exception as e:
        logger.error(f"Error getting subtasks: {str(e)}")
        return {"error": str(e), "subtasks": [], "count": 0}


# Define resources for retrieving JIRA information

@mcp.resource("jira://issue/{issue_key}")
def get_issue_resource(issue_key: str) -> str:
    """
    Get information about a specific JIRA issue as a formatted string.
    
    Args:
        issue_key: The JIRA issue key (e.g., "PROJECT-123")
        
    Returns:
        Formatted string with issue information
    """
    ctx = Context.get()
    jira_client = ctx.request_context.lifespan_context.jira_client
    try:
        issue = jira_client.get_issue(issue_key)
        
        # Create a formatted string with issue details
        result = [
            f"# {issue['key']}: {issue['summary']}",
            f"Status: {issue['status']}",
            f"Type: {issue['issuetype']}",
            f"Priority: {issue['priority']}",
            f"Assignee: {issue['assignee']}",
            f"Reporter: {issue['reporter']}",
            "",
            "## Description",
            issue['description'] or "No description provided.",
            "",
        ]
        
        # Add labels if present
        if issue['labels']:
            result.extend([
                "## Labels",
                ", ".join(issue['labels']),
                "",
            ])
        
        # Add components if present
        if issue['components']:
            result.extend([
                "## Components",
                ", ".join(issue['components']),
                "",
            ])
        
        # Add versions if present
        if issue['affectedVersions']:
            result.extend([
                "## Affected Versions",
                ", ".join(issue['affectedVersions']),
                "",
            ])
        
        if issue['fixVersions']:
            result.extend([
                "## Fix Versions",
                ", ".join(issue['fixVersions']),
                "",
            ])
        
        # Add parent information if present
        if 'parent' in issue:
            result.extend([
                "## Parent Issue",
                f"{issue['parent']['key']}: {issue['parent']['summary']}",
                "",
            ])
        
        return "\n".join(result)
    except Exception as e:
        logger.error(f"Error getting issue resource: {str(e)}")
        return f"Error retrieving issue {issue_key}: {str(e)}"


@mcp.resource("jira://search/{encoded_jql}")
def search_issues_resource(encoded_jql: str) -> str:
    """
    Search for JIRA issues using JQL and return results as a formatted string.
    The JQL should be URL-encoded.
    
    Args:
        encoded_jql: URL-encoded JQL query string
        
    Returns:
        Formatted string with search results
    """
    ctx = Context.get()
    max_results = 10
    import urllib.parse
    
    jira_client = ctx.request_context.lifespan_context.jira_client
    try:
        # Decode the URL-encoded JQL
        jql = urllib.parse.unquote(encoded_jql)
        
        issues = jira_client.search_issues(jql, max_results)
        
        # Create a formatted string with search results
        result = [
            f"# JIRA Search Results",
            f"Query: {jql}",
            f"Found {len(issues)} issues",
            "",
        ]
        
        for issue in issues:
            result.extend([
                f"## {issue['key']}: {issue['summary']}",
                f"Status: {issue['status']}",
                f"Type: {issue['issuetype']}",
                f"Priority: {issue['priority']}",
                f"Assignee: {issue['assignee']}",
                "",
            ])
        
        return "\n".join(result)
    except Exception as e:
        logger.error(f"Error searching issues resource: {str(e)}")
        return f"Error searching issues: {str(e)}"


@mcp.resource("jira://comments/{issue_key}")
def get_issue_comments_resource(issue_key: str) -> str:
    """
    Get all comments for a specific JIRA issue as a formatted string.
    
    Args:
        issue_key: The JIRA issue key (e.g., "PROJECT-123")
        
    Returns:
        Formatted string with issue comments
    """
    ctx = Context.get()
    jira_client = ctx.request_context.lifespan_context.jira_client
    try:
        comments = jira_client.get_issue_comments(issue_key)
        
        # Create a formatted string with comments
        result = [
            f"# Comments for {issue_key}",
            f"Total comments: {len(comments)}",
            "",
        ]
        
        for comment in comments:
            result.extend([
                f"## Comment by {comment['author']} on {comment['created']}",
                comment['body'],
                "",
                "---",
                "",
            ])
        
        return "\n".join(result)
    except Exception as e:
        logger.error(f"Error getting issue comments resource: {str(e)}")
        return f"Error retrieving comments for {issue_key}: {str(e)}"


@mcp.resource("jira://links/{issue_key}")
def get_issue_links_resource(issue_key: str) -> str:
    """
    Get all links for a specific JIRA issue as a formatted string.
    
    Args:
        issue_key: The JIRA issue key (e.g., "PROJECT-123")
        
    Returns:
        Formatted string with issue links
    """
    ctx = Context.get()
    jira_client = ctx.request_context.lifespan_context.jira_client
    try:
        links = jira_client.get_issue_links(issue_key)
        
        # Create a formatted string with links
        result = [
            f"# Issue Links for {issue_key}",
            "",
        ]
        
        if not links:
            result.append("No links found for this issue.")
        
        for link_type, linked_issues in links.items():
            result.extend([
                f"## {link_type}",
                "",
            ])
            
            for issue in linked_issues:
                direction = "➡️" if issue['direction'] == 'outward' else "⬅️"
                result.append(f"{direction} {issue['key']} ({issue['status']}): {issue['summary']}")
            
            result.append("")
        
        return "\n".join(result)
    except Exception as e:
        logger.error(f"Error getting issue links resource: {str(e)}")
        return f"Error retrieving links for {issue_key}: {str(e)}"


if __name__ == "__main__":
    mcp.run(transport="stdio")


"""JIRA MCP server — FastMCP setup, tool registration, and prompts.

Every tool is a registration of a function from :mod:`mcp_jira.tools`, which the
CLI calls directly, so the two entry points cannot drift apart.
"""

import logging
import os
import sys

from mcp.server.fastmcp import FastMCP

from . import tools


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

# Registered under explicit names so the MCP tool surface stays jira_*.
mcp.tool(name="jira_search_issues")(tools.search_issues)
mcp.tool(name="jira_get_issue")(tools.get_issue)
mcp.tool(name="jira_create_issue")(tools.create_issue)
mcp.tool(name="jira_update_issue")(tools.update_issue)
mcp.tool(name="jira_transition_issue")(tools.transition_issue)
mcp.tool(name="jira_link_issues")(tools.link_issues)
mcp.tool(name="jira_add_remote_link")(tools.add_remote_link)
mcp.tool(name="jira_get_create_meta")(tools.get_create_meta)


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
    missing_vars = tools.missing_env()

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

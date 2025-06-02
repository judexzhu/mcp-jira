# JIRA MCP Server (Async)

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io)
[![UV](https://img.shields.io/badge/package%20manager-uv-blue)](https://docs.astral.sh/uv/)

A high-performance, asynchronous Model Context Protocol (MCP) server that integrates with JIRA using **stdio transport**, allowing AI assistants to:
- Connect to your company's JIRA instance with async operations
- Search for issues using JQL (JIRA Query Language) with concurrent processing
- Get detailed issue information including comments with improved performance
- Track issue relationships (links, parent/child, epics) efficiently
- Create new issues and update existing ones
- View available workflow transitions

## 🚀 Performance Features

This async implementation provides significant performance improvements over traditional synchronous JIRA clients:

- **Concurrent API Calls**: Process multiple JIRA requests simultaneously
- **Connection Pooling**: Efficient HTTP connection management with `aiohttp`
- **Rate Limiting**: Built-in throttling to respect JIRA API limits
- **Non-blocking I/O**: True async operations that don't block the event loop
- **Stdio Transport**: Optimized for MCP client integration
- **Clean Architecture**: Focused on essential tools without unnecessary complexity

### Performance Comparison
- **Synchronous**: Traditional blocking operations
- **Asynchronous**: Non-blocking concurrent operations with connection pooling

## Features

This MCP server provides functionality through MCP tools:

## MCP Tools

The server exposes the following MCP tools with `jira_` prefixes to avoid conflicts with other MCP servers (like GitHub):

| Tool | Description | Parameters | 
|------|-------------|------------|
| `jira_search_issues` | Search for JIRA issues using JQL | `jql`: JQL query string<br>`max_results`: Maximum number of results to return |
| `jira_get_issue_details` | Get detailed information about a specific JIRA issue | `issue_key`: The JIRA issue key (e.g., "PROJECT-123") |
| `jira_get_issue_comments` | Get all comments for a specific JIRA issue | `issue_key`: The JIRA issue key |
| `jira_get_issue_links` | Get all links for a specific JIRA issue | `issue_key`: The JIRA issue key |
| `jira_get_epic_issues` | Get all issues that belong to a specific epic | `epic_key`: The JIRA epic issue key |
| `jira_get_subtasks` | Get all subtasks for a specific JIRA issue | `issue_key`: The parent JIRA issue key |
| `jira_get_available_transitions` | Lists available workflow transitions for a given Jira issue | `issue_key`: The JIRA issue key |
| `jira_create_issue` | Creates a new issue in a specified Jira project | `project_key`: Key of the project<br>`summary`: Issue summary<br>`description`: Issue description<br>`issue_type_name`: Type of the issue<br>`assignee_name`: (Optional) Name of the assignee<br>`priority_name`: (Optional) Name of the priority<br>`labels`: (Optional) List of labels<br>`custom_fields`: (Optional) Dictionary of custom fields |

## Architecture

The server uses a **clean, tool-focused architecture**:

- **8 MCP Tools**: All essential JIRA operations as simple, focused functions
- **No Resources**: Simplified design without MCP resources for easier maintenance
- **Async Client**: High-performance `AsyncJiraClient` with connection pooling
- **Comprehensive Logging**: Detailed logging for monitoring and debugging

This approach provides:
- ✅ **Simplicity**: Easy to understand and maintain
- ✅ **Performance**: Async operations with connection pooling
- ✅ **Reliability**: Focused functionality with comprehensive error handling
- ✅ **Flexibility**: All essential JIRA operations available through clean tool interfaces

## Setup

### Prerequisites

- Python 3.13+
- uv package manager
- JIRA API token from your Atlassian account

### Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/mcp-jira.git
   cd mcp-jira
   ```

2. Install dependencies:
   ```bash
   uv sync
   ```

3. Create a `.env` file with your JIRA credentials:
   ```bash
   cp config.env.example .env
   ```

4. Edit the `.env` file with your JIRA credentials:
   ```env
   # JIRA Configuration
   JIRA_SERVER_URL=https://your-company.atlassian.net
   JIRA_API_TOKEN=your_api_token_here
   
   # Performance Configuration
   MAX_CONCURRENT_REQUESTS=2
   LOG_LEVEL=INFO
   
   # Timeouts (in seconds)
   REQUEST_TIMEOUT=30
   CONNECT_TIMEOUT=10
   ```

### Running the Server

This is a **STDIO MCP Server** designed to be used with MCP clients like Claude Desktop. 

The server is designed to be used with MCP clients. For Claude Desktop:

1. **Add to Claude Desktop Configuration**:
   
   ```json
   {
     "mcpServers": {
       "jira": {
         "command": "python",
         "args": ["/path/to/your/jira_mcp_server.py"],
         "env": {
           "JIRA_SERVER_URL": "https://your-company.atlassian.net",
           "JIRA_API_TOKEN": "your_api_token_here"
         }
       }
     }
   }
   ```
2. **Restart Claude Desktop** to load the new server configuration.



### Environment Variables

The server uses the following environment variables with built-in defaults:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `JIRA_SERVER_URL` | Your JIRA instance URL | None | ✅ **Required** |
| `JIRA_API_TOKEN` | Your JIRA API token | None | ✅ **Required** |
| `MAX_CONCURRENT_REQUESTS` | Max concurrent requests & rate limit (req/sec) | `2` | Optional |
| `REQUEST_TIMEOUT` | HTTP request timeout (seconds) | `30` | Optional |
| `CONNECT_TIMEOUT` | HTTP connection timeout (seconds) | `10` | Optional |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `ERROR` | Optional |
| `LOG_TO_STDOUT` | Enable stdout logging (interferes with MCP) | `false` | Optional |

**Only `JIRA_SERVER_URL` and `JIRA_API_TOKEN` are required** - all other settings have sensible defaults.

### Logging

The server includes comprehensive logging:
- **Console Output**: Real-time status and errors
- **Log File**: Detailed logs saved to `jira_mcp_server.log`
- **Configurable Levels**: Set `LOG_LEVEL` in your `.env` file

Log levels:
- `DEBUG`: Detailed debugging information
- `INFO`: General operational messages (default)
- `WARNING`: Warning messages and rate limiting notices
- `ERROR`: Error conditions

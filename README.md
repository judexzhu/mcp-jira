# JIRA MCP Server (Async)

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io)
[![UV](https://img.shields.io/badge/package%20manager-uv-blue)](https://docs.astral.sh/uv/)

An async Model Context Protocol (MCP) server for JIRA integration via stdio transport. Supports both Atlassian Cloud and Server/DC instances.

## MCP Tools

6 tools covering the full issue lifecycle, plus 2 prompt templates:

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `jira_search_issues` | Search issues using JQL (paginated) | `jql`, `max_results`, `start_at` |
| `jira_get_issue` | Get issue details, comments, links; optionally subtasks and transitions | `issue_key`, `include_subtasks`, `include_transitions` |
| `jira_create_issue` | Create a new issue | `project_key`, `summary`, `description`, `issue_type_name` |
| `jira_update_issue` | Update fields on an existing issue, optionally add a comment | `issue_key`, `summary`, `description`, `assignee`, `priority`, `labels`, `comment` |
| `jira_transition_issue` | Move an issue through a workflow transition | `issue_key`, `transition_id`, `comment` |
| `jira_get_create_meta` | Get required fields and allowed values before creating an issue | `project_key`, `issue_type` |

## Features

- **Cloud + Server/DC**: Auto-detects deployment type via `JIRA_USER_EMAIL` env var
- **Token optimization**: API responses transformed to 40-60% fewer tokens
- **ADF support**: Reads and writes Atlassian Document Format (Cloud v3)
- **Connection pooling**: `aiohttp` with configurable pool size
- **Rate limiting**: Built-in throttling with exponential backoff on 429s
- **Testable**: Injectable client via `_set_client()`, session injection for HTTP-level tests, 113 unit tests

## Setup

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- JIRA API token

### Installation

```bash
git clone https://github.com/judexzhu/mcp-jira.git
cd mcp-jira
uv sync
cp config.env.example .env
# Edit .env with your JIRA credentials
```

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `JIRA_SERVER_URL` | Your JIRA instance URL | — | Yes |
| `JIRA_API_TOKEN` | Your JIRA API token | — | Yes |
| `JIRA_USER_EMAIL` | Email for Cloud Basic Auth (enables Cloud mode) | — | Cloud only |
| `MAX_CONCURRENT_REQUESTS` | Max concurrent requests & rate limit (req/sec) | `2` | No |
| `REQUEST_TIMEOUT` | HTTP request timeout (seconds) | `30` | No |
| `CONNECT_TIMEOUT` | HTTP connection timeout (seconds) | `10` | No |
| `LOG_LEVEL` | Logging level | `ERROR` | No |
| `LOG_TO_STDOUT` | Enable stdout logging (breaks MCP stdio) | `false` | No |

### Claude Desktop

Add to your Claude Desktop MCP config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "jira": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mcp-jira", "python", "jira_mcp_server.py"],
      "env": {
        "JIRA_SERVER_URL": "https://your-company.atlassian.net",
        "JIRA_API_TOKEN": "your_api_token",
        "JIRA_USER_EMAIL": "you@company.com"
      }
    }
  }
}
```

### Claude Code

Add to your Claude Code MCP settings (`.claude/settings.json` or global `~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "jira": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mcp-jira", "python", "jira_mcp_server.py"],
      "env": {
        "JIRA_SERVER_URL": "https://your-company.atlassian.net",
        "JIRA_API_TOKEN": "your_api_token",
        "JIRA_USER_EMAIL": "you@company.com"
      }
    }
  }
}
```

Or add via CLI:

```bash
claude mcp add jira \
  -e JIRA_SERVER_URL=https://your-company.atlassian.net \
  -e JIRA_API_TOKEN=your_api_token \
  -e JIRA_USER_EMAIL=you@company.com \
  -- uv run --directory /path/to/mcp-jira python jira_mcp_server.py
```

Alternatively, skip the `-e` flags and put credentials in a `.env` file inside the mcp-jira directory — `load_dotenv()` picks them up automatically.

## Testing

```bash
# Unit tests (no credentials needed)
uv sync --group dev
uv run pytest tests/ -v
```

## Architecture

Two-file core:

- **`jira_mcp_server.py`** — 6 MCP tool functions + 2 prompt templates, each a thin wrapper delegating to the client
- **`jira_client.py`** — `AsyncJiraClient` with `JiraClientProtocol` seam, `_CloudFormat`/`_ServerFormat` adapters, auth, connection pooling, rate limiting, retry, and response transformation

Cloud vs Server/DC is detected by the presence of `JIRA_USER_EMAIL`. See `docs/adr/0001-cloud-detection-via-email.md` for the rationale.

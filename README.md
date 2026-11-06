# JIRA MCP Server (Async)

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io)
[![UV](https://img.shields.io/badge/package%20manager-uv-blue)](https://docs.astral.sh/uv/)

An async Model Context Protocol (MCP) server and a `jira` CLI for JIRA Cloud integration via stdio transport.

## MCP Tools

8 tools covering the full issue lifecycle, plus 2 prompt templates:

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `jira_search_issues` | Search issues using JQL (paginated) | `jql`, `max_results`, `start_at` |
| `jira_get_issue` | Get issue details, comments, links; optionally subtasks and transitions | `issue_key`, `include_subtasks`, `include_transitions` |
| `jira_create_issue` | Create a new issue | `project_key`, `summary`, `description`, `issue_type_name` |
| `jira_update_issue` | Update fields on an existing issue, optionally add a comment | `issue_key`, `summary`, `description`, `assignee`, `priority`, `labels`, `comment` |
| `jira_transition_issue` | Move an issue through a workflow transition | `issue_key`, `transition_id`, `comment` |
| `jira_link_issues` | Link two issues with a typed relationship | `issue_key`, `target_key`, `link_type` |
| `jira_add_remote_link` | Attach a web link, such as a pull request, to an issue | `issue_key`, `url`, `title` |
| `jira_get_create_meta` | Get required fields and allowed values before creating an issue | `project_key`, `issue_type` |

## Features

- **Cloud only**: JIRA Cloud v3 — Basic Auth, ADF, `accountId` assignees
- **Two entry points, one implementation**: the MCP tools and the `jira` CLI call the same operations in `mcp_jira/tools.py`
- **Token optimization**: API responses transformed to 40-60% fewer tokens
- **ADF support**: Reads and writes Atlassian Document Format (Cloud v3)
- **Connection pooling**: `aiohttp` with configurable pool size
- **Rate limiting**: Built-in throttling with exponential backoff on 429s
- **Testable**: Injectable client via `_set_client()`, session injection for HTTP-level tests, 238 unit tests, 98% line coverage

## CLI

The `jira` console script has 12 commands: seven cover the eight MCP tools, plus five extras (`comment`, `comments`, `project`, `field`, `me`). JSON by default, so it pipes into `jq`; `-o table` and `-o md` are for reading.

```bash
jira me                                              # check credentials
jira search "assignee = currentUser()" -o table
jira issue OCPBUGS-1234 --transitions
jira meta OCPBUGS --issue-type Bug                  # required fields before creating
jira create OCPBUGS "etcd leader flaps" "Step 1..." Bug --priority Major
jira update OCPBUGS-1234 --comment "Reproduced on 4.18.3"
jira transition OCPBUGS-1234 31 --comment "Fixed in 4.18.4"
jira link OCPBUGS-1234 OCPBUGS-5678 --type Blocks  # 1234 blocks 5678
jira link OCPBUGS-1234 https://github.com/o/r/pull/1 --web --title "Fix PR"
```

Run `jira --help` for the full command reference. `update` refuses to run with no field flags, because an empty `PUT` reports success while changing nothing.

An agent-facing skill describing when and how to use the CLI is at `skills/jira-cli/SKILL.md`.

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
| `JIRA_USER_EMAIL` | Email for Basic Auth | — | Yes |
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

Add `--scope project` to install at project level (`.claude/settings.json`) instead of user level.

Alternatively, skip the `-e` flags and put credentials in a `.env` file inside the mcp-jira directory — `load_dotenv()` picks them up automatically.

## Testing

```bash
# Unit tests (no credentials needed)
uv sync --group dev
uv run pytest tests/ -v
```

## Architecture

One package, plus a root shim so existing MCP client configs keep working:

- **`mcp_jira/tools.py`** — the operations layer: the shared client and one async function per JIRA operation
- **`mcp_jira/server.py`** — registers eight operations as MCP tools under their `jira_*` names, plus 2 prompt templates
- **`mcp_jira/cli.py`** — the `jira` click CLI over the same operations
- **`mcp_jira/client.py`** — `AsyncJiraClient` for JIRA Cloud v3, with `JiraClientProtocol`, retry, throttling, and the `_transform_*` response flatteners
- **`jira_mcp_server.py`** — root shim re-exporting `main` and `mcp` from `mcp_jira.server`

Cloud is the only supported deployment: the v3 prefix and search endpoint are module constants, and `JIRA_USER_EMAIL` is required. See `docs/adr/0002-cloud-only-and-shared-operations-layer.md` for the rationale, and `docs/adr/0001-cloud-detection-via-email.md` for the decision this supersedes.

# JIRA MCP Server

A Model Context Protocol (MCP) server that integrates with JIRA, allowing AI assistants to:
- Connect to your company's JIRA instance
- Search for issues using JQL
- Get detailed issue information including comments
- Track issue relationships (mentions, links, parent/child, epics)

## Features

This MCP server provides tools and resources for working with JIRA:

### Tools
- `search_issues`: Search for issues using JQL
- `get_issue_details`: Get detailed information about a specific issue
- `get_issue_comments`: Get all comments for an issue
- `get_issue_links`: Get all links for an issue
- `get_epic_issues`: Get all issues that belong to an epic
- `get_subtasks`: Get all subtasks for an issue

### Resources
- `jira://issue/{issue_key}`: Get information about a specific issue
- `jira://search/{encoded_jql}`: Search for issues using URL-encoded JQL
- `jira://comments/{issue_key}`: Get all comments for an issue
- `jira://links/{issue_key}`: Get all links for an issue

## Setup

### Prerequisites

- Python 3.8+
- JIRA API token

### Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/mcp-jira.git
   cd mcp-jira
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the `src` directory with your JIRA credentials:
   ```bash
   cp src/.env.example src/.env
   ```

4. Edit the `.env` file with your JIRA credentials:
   ```
   JIRA_SERVER_URL=https://your-company.atlassian.net
   JIRA_API_TOKEN=your_api_token_here
   JIRA_EMAIL=your_email@company.com
   ```

### Running the Server

Run the server:

```bash
cd src
python jira_mcp_server.py
```

The server will start on `http://127.0.0.1:8000`.

### Installing in Claude Desktop

To install the MCP server in Claude Desktop:

1. Install the MCP CLI:
   ```bash
   pip install "mcp[cli]"
   ```

2. Install the server in Claude Desktop:
   ```bash
   cd src
   mcp install jira_mcp_server.py
   ```

3. Open Claude Desktop and enable the "JIRA MCP Server" from the MCP Servers panel.

## Usage Examples

### Searching for Issues

```
I need to find all high-priority bugs in the PROJ project.
```

Claude will use the `search_issues` tool with appropriate JQL:

```
project = PROJ AND priority = High AND issuetype = Bug
```

### Getting Issue Details

```
Can you tell me about PROJ-123?
```

Claude will use the `get_issue_details` tool to get information about the issue.

### Analyzing Issue Relationships

```
Show me all the issues linked to PROJ-123.
```

Claude will use the `get_issue_links` tool to find related issues.

### Working with Epics

```
What issues are in the PROJ-456 epic?
```

Claude will use the `get_epic_issues` tool to list all issues in the epic.

## Authentication

This MCP server uses token-based authentication with JIRA. You'll need to create an API token in your Atlassian account:

1. Log in to https://id.atlassian.com/
2. Go to Security → API tokens
3. Click "Create API token"
4. Use this token in your `.env` file

## Troubleshooting

If you encounter issues:

1. Ensure your JIRA credentials are correct in the `.env` file
2. Check that your JIRA API token has the necessary permissions
3. Look at the server logs for error messages
4. Make sure your JIRA customfields match the ones in the code (you might need to adjust the field IDs)

## Advanced Configuration

You can set the following environment variables:
- `PORT`: Change the server port (default: 8000)
- `HOST`: Change the server host (default: 127.0.0.1)

## License

MIT

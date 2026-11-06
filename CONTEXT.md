# JIRA MCP Server

An async MCP server and command-line tool over JIRA's REST API. The only supported deployment is Atlassian Cloud (`redhat.atlassian.net` in practice), which means Basic Auth and the v3 API. The core design concern is reducing token consumption by transforming JIRA's verbose, deeply nested responses into minimal flat structures.

## Language

**Cloud**:
The only supported JIRA deployment: Atlassian Cloud, addressed with REST API v3. Authentication is always Basic Auth, an `JIRA_USER_EMAIL` and an API token together, and rich-text fields are always ADF.
_Avoid_: hosted JIRA, SaaS JIRA, on-prem JIRA

**ADF**:
Atlassian Document Format — the rich-text JSON structure used by Cloud v3 API fields like description and comment body. Converted to plain text on read, and produced from plain text on write.
_Avoid_: rich text, JSON body

**Transform**:
A `_transform_*` helper function that flattens a JIRA API response object into a minimal dict, stripping nested wrappers and omitting empty fields. The primary token-optimization mechanism (40-60% reduction per response).
_Avoid_: serializer, formatter, mapper

**Operation**:
One async function in `mcp_jira/tools.py` that performs a JIRA call against the shared client. Operations are the single implementation both entry points reach for, so no JIRA behaviour lives in the server or the CLI.
_Avoid_: service method, action, handler

**Tool**:
An MCP tool, the registration of an Operation under a `jira_*` name by `mcp_jira/server.py`. A Tool is how an LLM reaches an Operation.
_Avoid_: endpoint, resource, function

**Command**:
A `click` command in `mcp_jira/cli.py`, the CLI's way of reaching an Operation. A Command is how a human or shell script reaches an Operation. Seven Commands cover the eight Tools, because `link` reaches both `link_issues` and `add_remote_link`; the other five (`comment`, `comments`, `project`, `field`, `me`) have no Tool.
_Avoid_: subcommand, verb, tool (when meaning Command)

**Issue Key**:
The `PROJECT-123` identifier format used by JIRA. The primary handle for all single-issue operations.
_Avoid_: issue ID, ticket number

**Issue Link**:
A typed, directional relationship between two issues, read from `fields.issuelinks` and created with `POST /rest/api/3/issueLink`. The issue that links is the outward side and the one linked to is the inward side, so `A B --type Blocks` means A blocks B. Type names come from the instance and are case-sensitive.
_Avoid_: relation, dependency (one kind of link, not the concept)

**Web Link**:
A URL attached to a single issue, such as a pull request or merge request. JIRA stores it on `/issue/{KEY}/remotelink`, not in `fields.issuelinks`, so it points at no other issue and JIRA requires link text with it. The API, and so the code, call this a remote link.
_Avoid_: external link, attachment

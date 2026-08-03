# JIRA MCP Server

An async MCP server that bridges JIRA's REST API with MCP clients (LLMs). The primary consumer is Red Hat's Cloud instance (`redhat.atlassian.net`), but the server maintains Server/DC compatibility for self-hosted deployments. The core design concern is reducing token consumption by transforming JIRA's verbose, deeply nested responses into minimal flat structures.

## Language

**Cloud instance**:
A JIRA deployment hosted on Atlassian Cloud (e.g. `redhat.atlassian.net`). Detected at runtime by the presence of `JIRA_USER_EMAIL`. Uses Basic Auth and the v3 search endpoint. This is the primary deployment target.
_Avoid_: hosted JIRA, SaaS JIRA

**Server/DC instance**:
A self-hosted JIRA deployment (Server or Data Center edition). Uses Bearer token auth and the v2 search endpoint. Kept compatible as a secondary target.
_Avoid_: on-prem JIRA, self-managed

**ADF**:
Atlassian Document Format — the rich-text JSON structure returned by Cloud v3 API fields like description and comment body. Must be converted to plain text before returning to MCP clients.
_Avoid_: rich text, JSON body

**Transform**:
A `_transform_*` helper function that flattens a JIRA API response object into a minimal dict, stripping nested wrappers and omitting empty fields. The primary token-optimization mechanism (40-60% reduction per response).
_Avoid_: serializer, formatter, mapper

**Tool**:
An `@mcp.tool()` function exposed by the MCP server. Each tool is a thin async wrapper that validates inputs and delegates to the JIRA client. The server currently exposes six tools.
_Avoid_: endpoint, handler, route, action

**Issue Key**:
The `PROJECT-123` identifier format used by JIRA. The primary handle for all single-issue operations.
_Avoid_: issue ID, ticket number

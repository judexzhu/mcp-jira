---
status: accepted
---

# Cloud-only, and one shared operations layer behind two entry points

Supersedes [0001](0001-cloud-detection-via-email.md), which described inferring Cloud vs Server/DC from the presence of `JIRA_USER_EMAIL`.

## Cloud is the only deployment

The client targets JIRA Cloud exclusively: REST API v3, Basic Auth (`email:token`), ADF for rich text, `accountId` for assignees. The `_CloudFormat`/`_ServerFormat` adapter pair, the `is_cloud` flag, the Bearer-token auth branch, and the v2 search endpoint are gone. `JIRA_USER_EMAIL` is now required, and constructing `AsyncJiraClient` without it raises immediately rather than silently falling back to Bearer auth.

The reasoning: nothing in this repository targets Server/DC. The instance everyone uses is `redhat.atlassian.net`, and Server/DC support existed only as an untested secondary path. ADR 0001's own tradeoff section anticipated the problem — "if Atlassian ever supports email-less Cloud auth or email-based Server/DC auth, this heuristic breaks" — but the real defect was that a missing credential silently selected a different, wrong deployment instead of failing. Two format adapters also meant every new endpoint had to be correct twice, and only the Cloud half was ever exercised against a live instance.

The cost: JIRA Server/DC is unsupported. Anyone wanting it would re-add a second format seam; the diff is roughly the one being deleted here, available in git history before this ADR.

## One operations layer, two entry points

`mcp_jira/tools.py` owns the JIRA calls and the client lifecycle. `mcp_jira/server.py` registers six of those operations as MCP tools under their existing `jira_*` names. `mcp_jira/cli.py` calls the same functions behind `click` commands. Neither entry point constructs a client.

The reasoning: before this, the MCP server built its client from `JIRA_SERVER_URL`/`JIRA_API_TOKEN`/`JIRA_USER_EMAIL` while an earlier CLI built its own from `JIRA_BASE_URL`/`JIRA_AUTH_BASIC`, and the two disagreed about which variables configure the tool. Anything that can be configured two ways will eventually be configured one way in one place and the other way in the other. A shared operations layer makes drift impossible rather than merely discouraged, and it matches the layout of the sibling servers (`redhat-api-mcp`, `mcp-slack`).

The cost: `tools.py` holds a process-global client with a `_set_client` seam for tests, which is less pure than passing a client explicitly. The alternative — every entry point wiring its own client — is exactly the arrangement this ADR exists to prevent.

The trade-off accepted: the CLI and the MCP server cannot diverge in behaviour. A CLI-only convenience must be implemented as an Operation plus a Command, or not at all.

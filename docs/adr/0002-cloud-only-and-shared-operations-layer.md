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

The reasoning: drift between two entry points is not hypothetical in this codebase. Before this change `jira_mcp_server.py` held the requirement in two places that already disagreed. `main()` guarded `JIRA_SERVER_URL` and `JIRA_API_TOKEN` only (`jira_mcp_server.py:255`), while the client-building path immediately below consumed those plus `JIRA_USER_EMAIL` (`:57-60`). A run missing the email passed the startup guard and was consumed anyway, which is how a missing credential came to select Bearer auth instead of failing. Duplicated configuration is the failure mode a shared operations layer removes at the root rather than leaving to discipline. One tuple, `REQUIRED_ENV` in `tools.py`, is now read by both `get_client()` and `server.main()`, so the guard and the consumer cannot disagree. The layout also matches the sibling servers (`redhat-api-mcp`, `mcp-slack`), so the three are navigable the same way.

The cost: `tools.py` holds a process-global client with a `_set_client` seam for tests, which is less pure than passing a client explicitly. The alternative — every entry point wiring its own client — is exactly the arrangement this ADR exists to prevent.

The trade-off accepted: the CLI and the MCP server cannot diverge in behaviour. A CLI-only convenience must be implemented as an Operation plus a Command, or not at all.

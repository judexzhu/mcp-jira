---
name: jira
description: >
  Use the `jira` CLI to search, read, create, and update JIRA Cloud issues.
  Trigger this skill whenever the user asks about JIRA tickets or issues: looking
  up an issue by key, running a JQL query or search, finding issues assigned to
  them or a teammate, reading an issue's comments or linked issues, filing a new
  bug or task, commenting on an issue, changing an issue's status, or finding the
  required fields of a project before creating a ticket — even if they don't say
  "jira" explicitly. Common triggers include "OCPBUGS-1234", "what's the status of
  my tickets", "file a bug", "move this issue to In Progress", "who is assigned",
  "search JQL for", "add a comment to", "check the fields for project X".
---

# jira — JIRA Cloud CLI

`jira` is a globally installed CLI over JIRA Cloud. Requires `JIRA_SERVER_URL`, `JIRA_API_TOKEN`, and `JIRA_USER_EMAIL` in the environment.

Run `jira --help` for the full command reference with all flags and examples.

## Commands

| Command | Purpose |
|---------|---------|
| `jira search JQL` | Search issues with JQL (paginated via `--max-results` / `--start-at`) |
| `jira issue KEY` | One issue with comments and links; `--subtasks`, `--transitions` |
| `jira create PROJECT SUMMARY DESC TYPE` | Create an issue |
| `jira update KEY` | Update fields; `--summary`, `--description`, `--assignee`, `--priority`, `--label`, `--comment`, `--field` |
| `jira transition KEY TRANSITION_ID` | Move through a workflow |
| `jira meta PROJECT` | Issue types, or required fields for `--issue-type NAME` |
| `jira comment KEY TEXT` | Add a comment |
| `jira comments KEY` | An issue's comments, one page at a time |
| `jira project PROJECT` | One project |
| `jira field` | All fields with their ids |
| `jira me` | The authenticated account |

## Tips

- **`jira me` is the credential check.** Run it first if a command fails with an auth error.
- **Output is JSON by default**, so it pipes into `jq`. Add `-o table` or `-o md` for reading. Table output truncates long cells at 60 characters; use JSON when you need a full description.
- **`update` refuses to run with no field flags.** This is deliberate: an empty `PUT` reports success while changing nothing.
- **Find a transition id before transitioning.** `jira issue KEY --transitions` lists ids and target states; `jira transition` takes the id, not the state name.
- **Assignees are `accountId` strings on Cloud**, not usernames or emails. Get one from an existing issue's `jira issue KEY` output or from `jira search`.
- **Check `jira meta PROJECT --issue-type TYPE` before creating** in an unfamiliar project — custom required fields will otherwise fail the create.
- **`--field` takes a raw JSON object** merged into the payload, for custom fields: `--field '{"customfield_12345": {"id": "67890"}}'`. Use `jira field` to find the id and type.
- **`--label` is repeatable** and replaces the whole label list on `update`.
- **Descriptions are plain text**, converted to ADF on write. Markdown is not interpreted.

## Pagination

`search` and `comments` are offset-paginated. Loop with `--start-at` until you get fewer results than `--max-results`:

```bash
jira search "project = OCPBUGS AND status = Open" --max-results 50 --start-at 0
jira search "project = OCPBUGS AND status = Open" --max-results 50 --start-at 50
```

## Exit codes

- `0` — success
- `1` — HTTP or transport error; the JIRA message is on stderr, stdout stays empty
- `2` — configuration or usage error (missing env var, bad `--field` JSON, empty `update`)

Because stdout carries only the result, `jira ... > out.json` is safe to run even when the command fails.

"""JIRA command line interface.

Configuration comes from the environment, shared with the MCP server:

    JIRA_SERVER_URL     instance URL (https://your-company.atlassian.net)
    JIRA_API_TOKEN      API token
    JIRA_USER_EMAIL     the account the token belongs to

JSON is the default output so ``jira search ... | jq`` composes; ``-o table`` and
``-o md`` are for reading at a terminal.
"""

import asyncio
import json
import sys
from typing import Any, Awaitable, Callable, Dict, List

import click

from . import tools
from .client import JiraHttpError

EXIT_HTTP_ERROR = 1
EXIT_CONFIG_ERROR = 2

_output_option = click.option(
    "--output", "-o",
    type=click.Choice(["json", "table", "md"]),
    default="json",
    show_default=True,
    help="Output format.",
)


def _jira_message(error: JiraHttpError) -> str:
    """JIRA's own explanation from an error body, falling back to the raw body."""
    fallback = error.body.strip() or error.reason
    try:
        payload = json.loads(error.body)
    except ValueError:
        return fallback
    if not isinstance(payload, dict):
        return fallback

    messages = [str(message) for message in payload.get("errorMessages") or []]
    errors = payload.get("errors") or {}
    if isinstance(errors, dict):
        messages.extend(f"{field}: {message}" for field, message in errors.items())
    return "; ".join(messages) if messages else fallback


def _fail(message: str, exit_code: int) -> None:
    click.echo(f"error: {message}", err=True)
    sys.exit(exit_code)


def _load(jql_or_none: Any) -> Any:
    """Parse a JSON flag value, failing with the flag name rather than a traceback."""
    if jql_or_none is None:
        return None
    try:
        return json.loads(jql_or_none)
    except ValueError as error:
        raise click.BadParameter(f"expected JSON: {error}")


async def _call(call: Callable[[], Awaitable[Any]]) -> Any:
    """Run one command against the shared client, closing it afterwards.

    The client is built inside the loop because aiohttp needs a running loop to
    open its session.
    """
    try:
        return await call()
    finally:
        await tools.close_client()


def _run(call: Callable[[], Awaitable[Any]], output: str = "json") -> None:
    """Run one call and render its result."""
    try:
        result = asyncio.run(_call(call))
    except JiraHttpError as error:
        _fail(f"HTTP {error.status} {error.reason}: {_jira_message(error)}", EXIT_HTTP_ERROR)
    except ValueError as error:
        _fail(str(error).strip("'\""), EXIT_CONFIG_ERROR)
    except Exception as error:
        _fail(str(error), EXIT_HTTP_ERROR)
    _emit(result, output)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    return str(value).replace("\n", " ")


CELL_MAX = 60


def _truncate(text: str, limit: int = CELL_MAX) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _print_table(headers: List[str], rows: List[List[str]]) -> None:
    if not rows:
        click.echo("No results.")
        return
    rows = [[_truncate(cell) for cell in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    click.echo("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    click.echo("  ".join("-" * w for w in widths))
    for row in rows:
        click.echo("  ".join(cell.ljust(w) for cell, w in zip(row, widths)))


def _md_table(headers: List[str], rows: List[List[str]]) -> str:
    def esc(text: str) -> str:
        return text.replace("|", "\\|")

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(esc(cell) for cell in row) + " |")
    return "\n".join(lines)


def _md_dict(data: Dict[str, Any]) -> str:
    lines = []
    for key, value in data.items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            headers = list(value[0].keys())
            rows = [[_cell(item.get(h)) for h in headers] for item in value]
            lines.append(f"### {key}\n")
            lines.append(_md_table(headers, rows))
        elif isinstance(value, list):
            lines.append(f"**{key}:** {', '.join(_cell(item) for item in value)}")
        elif isinstance(value, dict):
            lines.append(f"**{key}:**\n")
            for sub_key, sub_value in value.items():
                lines.append(f"- {sub_key}: {_cell(sub_value)}")
        else:
            lines.append(f"**{key}:** {_cell(value)}")
    return "\n\n".join(lines)


def _print_dict(data: Dict[str, Any]) -> None:
    for key, value in data.items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            headers = list(value[0].keys())
            rows = [[_cell(item.get(h)) for h in headers] for item in value]
            click.echo(f"{key}:")
            _print_table(headers, rows)
        elif isinstance(value, list):
            click.echo(f"{key}: {_cell(value)}")
        elif isinstance(value, dict):
            click.echo(f"{key}:")
            for sub_key, sub_value in value.items():
                click.echo(f"  {sub_key}: {_cell(sub_value)}")
        else:
            click.echo(f"{key}: {_cell(value)}")


def _rows(data: Any) -> tuple[List[str], List[List[str]]]:
    """Pick the one list worth tabulating out of a result and name its columns."""
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                headers = list(value[0].keys())
                return headers, [[_cell(item.get(h)) for h in headers] for item in value]
    return [], []


def _emit(data: Any, output: str) -> None:
    if output == "json":
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
    elif output == "md":
        click.echo(_md_dict(data) if isinstance(data, dict) else _cell(data))
    elif isinstance(data, dict):
        headers, rows = _rows(data)
        if headers:
            _print_table(headers, rows)
        else:
            _print_dict(data)
    else:
        click.echo(_cell(data))


EPILOG = """
Command Details:

  search JQL [--max-results N] [--start-at N] [-o json|table|md]
    Search issues with JQL.
    $ jira search "project = OCPBUGS AND status = Open" --max-results 20 -o table

  issue KEY [--subtasks] [--transitions] [-o json|table|md]
    Show one issue, with its comments and links.
    $ jira issue OCPBUGS-1234 --transitions

  create PROJECT SUMMARY DESCRIPTION TYPE [--assignee ID] [--priority NAME]
         [--label L ...] [--field JSON] [-o json|table|md]
    Create an issue. DESCRIPTION is plain text, converted to ADF.
    $ jira create OCPBUGS "etcd leader flaps" "Step 1. ..." Bug --priority Major

  update KEY [--summary S] [--description D] [--assignee ID] [--priority NAME]
         [--label L ...] [--comment TEXT] [--field JSON] [-o json|table|md]
    Update fields on an issue. Refuses to run with no field flags.
    $ jira update OCPBUGS-1234 --comment "Reproduced on 4.18.3"

  transition KEY TRANSITION_ID [--comment TEXT] [-o json|table|md]
    Move an issue through its workflow. Find ids with `jira issue KEY --transitions`.
    $ jira transition OCPBUGS-1234 31 --comment "Fixed in 4.18.4"

  meta PROJECT [--issue-type NAME] [-o json|table|md]
    List a project's issue types, or the required fields for one type.
    $ jira meta OCPBUGS --issue-type Bug

  comment KEY TEXT [-o json|table|md]
    Add a comment.
    $ jira comment OCPBUGS-1234 "Confirmed against 4.18.3"

  comments KEY [--max-results N] [--start-at N] [-o json|table|md]
    List an issue's comments, one page at a time.

  project PROJECT [-o json|table|md]
    Show one project.

  field [-o json|table|md]
    List the fields defined on the instance, with ids for --field.

  me [-o json|table|md]
    Show the account the token authenticates as. Use it to check credentials.

--field takes a raw JSON object merged into the custom field payload:
  $ jira update OCPBUGS-1234 --field '{"customfield_12345": {"id": "67890"}}'

Environment Variables:
  JIRA_SERVER_URL    Instance URL (required)
  JIRA_API_TOKEN     API token (required)
  JIRA_USER_EMAIL    Account the token belongs to (required)
"""


class JiraGroup(click.Group):
    def format_epilog(self, ctx, formatter):
        if self.epilog:
            formatter.write(self.epilog)


@click.group(cls=JiraGroup, epilog=EPILOG)
@click.version_option(package_name="mcp-jira")
def cli() -> None:
    """JIRA CLI — query and update JIRA Cloud from the command line."""


@cli.command()
@click.argument("jql")
@click.option("--max-results", type=int, default=50, show_default=True,
              help="Maximum number of issues to return.")
@click.option("--start-at", type=int, default=0, show_default=True,
              help="Index of the first issue to return.")
@_output_option
def search(jql: str, max_results: int, start_at: int, output: str) -> None:
    """Search issues with JQL."""
    _run(lambda: tools.search_issues(jql, max_results=max_results, start_at=start_at), output)


@cli.command()
@click.argument("key")
@click.option("--subtasks", is_flag=True, help="Include subtasks (extra request).")
@click.option("--transitions", is_flag=True,
              help="Include available transitions (extra request).")
@_output_option
def issue(key: str, subtasks: bool, transitions: bool, output: str) -> None:
    """Show one issue."""
    _run(lambda: tools.get_issue(
        key, include_subtasks=subtasks, include_transitions=transitions), output)


@cli.command()
@click.argument("project_key")
@click.argument("summary")
@click.argument("description")
@click.argument("issue_type")
@click.option("--assignee", default=None, help="Assignee accountId.")
@click.option("--priority", default=None, help="Priority name (e.g. Major).")
@click.option("--label", "labels", multiple=True, help="Label (repeatable).")
@click.option("--field", "fields", default=None, help="Extra fields as a JSON object.")
@_output_option
def create(project_key: str, summary: str, description: str, issue_type: str,
           assignee: str, priority: str, labels: tuple, fields: str,
           output: str) -> None:
    """Create an issue."""
    custom_fields = _load(fields)
    _run(lambda: tools.create_issue(
        project_key, summary, description, issue_type,
        assignee_name=assignee, priority_name=priority,
        labels=list(labels) or None, custom_fields=custom_fields), output)


@cli.command()
@click.argument("key")
@click.option("--summary", default=None, help="New summary.")
@click.option("--description", default=None, help="New description (plain text).")
@click.option("--assignee", default=None, help="New assignee accountId.")
@click.option("--priority", default=None, help="New priority name.")
@click.option("--label", "labels", multiple=True, help="Label (repeatable, replaces existing).")
@click.option("--comment", default=None, help="Comment to add with the update.")
@click.option("--field", "fields", default=None, help="Extra fields as a JSON object.")
@_output_option
def update(key: str, summary: str, description: str, assignee: str, priority: str,
           labels: tuple, comment: str, fields: str, output: str) -> None:
    """Update fields on an issue."""
    if not any((summary, description, assignee, priority, labels, comment, fields)):
        raise click.UsageError(
            "no changes given; pass at least one of --summary, --description, "
            "--assignee, --priority, --label, --comment, --field"
        )
    custom_fields = _load(fields)
    _run(lambda: tools.update_issue(
        key, summary=summary, description=description, assignee=assignee,
        priority=priority, labels=list(labels) or None, comment=comment,
        custom_fields=custom_fields), output)


@cli.command()
@click.argument("key")
@click.argument("transition_id")
@click.option("--comment", default=None, help="Comment to add with the transition.")
@_output_option
def transition(key: str, transition_id: str, comment: str, output: str) -> None:
    """Transition an issue to a new workflow state."""
    _run(lambda: tools.transition_issue(key, transition_id, comment), output)


@cli.command()
@click.argument("key")
@click.argument("text")
@_output_option
def comment(key: str, text: str, output: str) -> None:
    """Add a comment to an issue."""
    _run(lambda: tools.add_comment(key, text), output)


@cli.command()
@click.argument("key")
@click.option("--max-results", type=int, default=50, show_default=True,
              help="Maximum number of comments to return.")
@click.option("--start-at", type=int, default=0, show_default=True,
              help="Index of the first comment to return.")
@_output_option
def comments(key: str, max_results: int, start_at: int, output: str) -> None:
    """List an issue's comments, one page at a time."""
    _run(lambda: tools.get_comments(key, max_results=max_results, start_at=start_at), output)


@cli.command()
@click.argument("project_key")
@click.option("--issue-type", default=None,
              help="Show required fields for this issue type instead of the type list.")
@_output_option
def meta(project_key: str, issue_type: str, output: str) -> None:
    """List a project's issue types, or the fields required for one type."""
    _run(lambda: tools.get_create_meta(project_key, issue_type), output)


@cli.command()
@click.argument("project_key")
@_output_option
def project(project_key: str, output: str) -> None:
    """Show one project."""
    _run(lambda: tools.get_project(project_key), output)


@cli.command()
@_output_option
def field(output: str) -> None:
    """List the fields defined on the instance."""
    _run(tools.get_fields, output)


@cli.command()
@_output_option
def me(output: str) -> None:
    """Show the user the token authenticates as."""
    _run(tools.get_myself, output)


if __name__ == "__main__":
    cli()

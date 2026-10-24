"""Read-only JIRA command line interface.

Every command writes one JSON document to stdout, so ``jira search ... | jq``
composes; diagnostics go to stderr only. Configuration comes from the
environment, never from a file or a secret-carrying flag:

    JIRA_BASE_URL                     instance URL, always required
    JIRA_AUTH_BASIC                   base64 of ``email:token``, as the
                                      OpenShell proxy injects it; wins when set
    JIRA_USER_EMAIL + JIRA_API_TOKEN  the local-use pair, when it is not set

Writes are deliberately absent: the L7 proxy in front of JIRA accepts six
read-only endpoints, and a write path the proxy rejects is worse than none.
"""

import asyncio
import base64
import json
import os
import sys
from typing import Any, Awaitable, Callable

import click

from jira_client import AsyncJiraClient, JiraHttpError

EXIT_HTTP_ERROR = 1
EXIT_CONFIG_ERROR = 2


class ConfigError(Exception):
    """Configuration the CLI cannot run without."""


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(f"missing {name}")
    return value


def client_from_env() -> AsyncJiraClient:
    """Build the read-only client from the environment variables above."""
    base_url = _require_env("JIRA_BASE_URL")

    basic_auth = os.getenv("JIRA_AUTH_BASIC")
    if basic_auth:
        try:
            decoded = base64.b64decode(basic_auth).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            raise ConfigError("malformed JIRA_AUTH_BASIC: expected base64 of email:token")
        email, separator, token = decoded.partition(":")
        if not separator or not email or not token:
            raise ConfigError("malformed JIRA_AUTH_BASIC: expected base64 of email:token")
        return AsyncJiraClient(base_url, token, user_email=email)

    return AsyncJiraClient(
        base_url,
        _require_env("JIRA_API_TOKEN"),
        user_email=_require_env("JIRA_USER_EMAIL"),
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


async def _read(client: AsyncJiraClient,
                call: Callable[[AsyncJiraClient], Awaitable[Any]]) -> Any:
    try:
        return await call(client)
    finally:
        await client.close()


def _run(call: Callable[[AsyncJiraClient], Awaitable[Any]]) -> None:
    """Run one read call and print its JSON result on stdout."""
    try:
        result = asyncio.run(_read(client_from_env(), call))
    except ConfigError as error:
        _fail(str(error), EXIT_CONFIG_ERROR)
    except JiraHttpError as error:
        _fail(f"HTTP {error.status} {error.reason}: {_jira_message(error)}", EXIT_HTTP_ERROR)
    except Exception as error:
        _fail(str(error), EXIT_HTTP_ERROR)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@click.group()
def main() -> None:
    """Read-only JIRA commands. JSON on stdout, diagnostics on stderr."""


@main.command()
@click.argument("jql")
@click.option("--max-results", type=int, default=50, show_default=True,
              help="Maximum number of issues to return.")
@click.option("--start-at", type=int, default=0, show_default=True,
              help="Index of the first issue to return.")
def search(jql: str, max_results: int, start_at: int) -> None:
    """Search issues with JQL."""
    _run(lambda client: client.search_issues(jql, max_results=max_results, start_at=start_at))


@main.command()
@click.argument("key")
@click.option("--subtasks", is_flag=True, help="Include subtasks (extra request).")
@click.option("--transitions", is_flag=True,
              help="Include available transitions (extra request).")
def issue(key: str, subtasks: bool, transitions: bool) -> None:
    """Show one issue."""
    _run(lambda client: client.get_issue(
        key, include_subtasks=subtasks, include_transitions=transitions))


@main.command()
@click.argument("key")
@click.option("--max-results", type=int, default=50, show_default=True,
              help="Maximum number of comments to return.")
@click.option("--start-at", type=int, default=0, show_default=True,
              help="Index of the first comment to return.")
def comments(key: str, max_results: int, start_at: int) -> None:
    """List an issue's comments, one page at a time."""
    _run(lambda client: client.get_comments(key, max_results=max_results, start_at=start_at))


@main.command()
@click.argument("key")
def project(key: str) -> None:
    """Show one project."""
    _run(lambda client: client.get_project(key))


@main.command()
def field() -> None:
    """List the fields defined on the instance."""
    _run(lambda client: client.get_fields())


@main.command()
def me() -> None:
    """Show the user the token authenticates as."""
    _run(lambda client: client.get_myself())


if __name__ == "__main__":
    main()

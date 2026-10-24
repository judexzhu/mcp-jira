"""Tests for the read-only CLI: JSON-only stdout, exit codes, env-var config."""

import asyncio
import base64
import json

import pytest
from click.testing import CliRunner

import cli
from jira_client import JiraHttpError


def make_runner():
    """CliRunner that keeps stdout and stderr apart on click 8.1 and 8.2."""
    try:
        return CliRunner(mix_stderr=False)
    except TypeError:  # click >= 8.2 always separates the streams
        return CliRunner()


class StubJiraClient:
    """Duck-typed AsyncJiraClient that records reads and can fail on demand."""

    def __init__(self):
        self.calls = []
        self.closed = False
        self.error = None

    def _result(self, name, **args):
        self.calls.append({"name": name, **args})
        if self.error is not None:
            raise self.error
        return {"command": name, "args": args}

    async def search_issues(self, jql, max_results=50, start_at=0):
        return self._result("search_issues", jql=jql, max_results=max_results, start_at=start_at)

    async def get_issue(self, issue_key, include_subtasks=False, include_transitions=False):
        return self._result("get_issue", issue_key=issue_key,
                            include_subtasks=include_subtasks,
                            include_transitions=include_transitions)

    async def get_comments(self, issue_key, max_results=50, start_at=0):
        return self._result("get_comments", issue_key=issue_key,
                            max_results=max_results, start_at=start_at)

    async def get_project(self, project_key):
        return self._result("get_project", project_key=project_key)

    async def get_fields(self):
        return self._result("get_fields")

    async def get_myself(self):
        return self._result("get_myself")

    async def close(self):
        self.closed = True


class RecordingClientClass:
    """Stands in for AsyncJiraClient so tests can read its constructor arguments."""

    instances = []

    def __init__(self, server_url, api_token, user_email=None, **kwargs):
        self.server_url = server_url
        self.api_token = api_token
        self.user_email = user_email
        RecordingClientClass.instances.append(self)


@pytest.fixture(autouse=True)
def jira_env(monkeypatch):
    """A complete environment; individual tests remove what they want missing."""
    monkeypatch.setenv("JIRA_BASE_URL", "https://jira.example.com")
    monkeypatch.setenv("JIRA_USER_EMAIL", "user@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "local-token")
    monkeypatch.delenv("JIRA_AUTH_BASIC", raising=False)


@pytest.fixture
def stub_client(monkeypatch):
    """Replace client construction so no request can leave the process."""
    stub = StubJiraClient()
    monkeypatch.setattr(cli, "client_from_env", lambda: stub)
    return stub


@pytest.fixture
def runner():
    return make_runner()


class TestCommandSurface:
    def test_client_is_built_inside_the_event_loop(self, monkeypatch):
        """aiohttp opens its session in the constructor, so it needs a running loop."""
        built = []

        def build_client():
            built.append(asyncio.get_running_loop())
            return StubJiraClient()

        monkeypatch.setattr(cli, "client_from_env", build_client)
        result = make_runner().invoke(cli.main, ["me"])
        assert result.exit_code == 0
        assert built

    def test_exposes_only_read_commands(self):
        assert set(cli.main.commands) == {
            "search", "issue", "comments", "project", "field", "me",
        }

    @pytest.mark.parametrize("argv", [
        ["search", "project=TEST"],
        ["issue", "TEST-1"],
        ["comments", "TEST-1"],
        ["project", "TEST"],
        ["field"],
        ["me"],
    ])
    def test_every_command_prints_one_json_document(self, runner, stub_client, argv):
        result = runner.invoke(cli.main, argv)
        assert result.exit_code == 0
        assert json.loads(result.stdout)["command"]
        assert result.stderr == ""
        assert stub_client.closed is True


class TestSearchCommand:
    def test_prints_search_result(self, runner, stub_client):
        result = runner.invoke(cli.main, ["search", "project=TEST"])
        payload = json.loads(result.stdout)
        assert payload["command"] == "search_issues"
        assert payload["args"]["jql"] == "project=TEST"

    def test_passes_paging_options(self, runner, stub_client):
        runner.invoke(cli.main, ["search", "project=TEST", "--max-results", "5", "--start-at", "10"])
        assert stub_client.calls == [{
            "name": "search_issues", "jql": "project=TEST", "max_results": 5, "start_at": 10,
        }]

    def test_paging_defaults(self, runner, stub_client):
        runner.invoke(cli.main, ["search", "project=TEST"])
        assert stub_client.calls[0]["max_results"] == 50
        assert stub_client.calls[0]["start_at"] == 0


class TestIssueCommand:
    def test_prints_issue(self, runner, stub_client):
        result = runner.invoke(cli.main, ["issue", "TEST-1"])
        assert json.loads(result.stdout)["command"] == "get_issue"

    def test_flags_default_to_off(self, runner, stub_client):
        runner.invoke(cli.main, ["issue", "TEST-1"])
        assert stub_client.calls[0]["include_subtasks"] is False
        assert stub_client.calls[0]["include_transitions"] is False

    def test_flags_map_to_client_flags(self, runner, stub_client):
        runner.invoke(cli.main, ["issue", "TEST-1", "--subtasks", "--transitions"])
        assert stub_client.calls[0] == {
            "name": "get_issue", "issue_key": "TEST-1",
            "include_subtasks": True, "include_transitions": True,
        }


class TestCommentsCommand:
    def test_prints_comments(self, runner, stub_client):
        result = runner.invoke(cli.main, ["comments", "TEST-1"])
        assert json.loads(result.stdout)["command"] == "get_comments"

    def test_passes_paging_options(self, runner, stub_client):
        runner.invoke(cli.main, ["comments", "TEST-1", "--max-results", "2", "--start-at", "4"])
        assert stub_client.calls == [{
            "name": "get_comments", "issue_key": "TEST-1", "max_results": 2, "start_at": 4,
        }]


class TestProjectCommand:
    def test_prints_project(self, runner, stub_client):
        result = runner.invoke(cli.main, ["project", "TEST"])
        payload = json.loads(result.stdout)
        assert payload["command"] == "get_project"
        assert payload["args"]["project_key"] == "TEST"


class TestFieldCommand:
    def test_prints_fields(self, runner, stub_client):
        result = runner.invoke(cli.main, ["field"])
        assert json.loads(result.stdout)["command"] == "get_fields"


class TestMeCommand:
    def test_prints_identity(self, runner, stub_client):
        result = runner.invoke(cli.main, ["me"])
        assert json.loads(result.stdout)["command"] == "get_myself"


class TestStdoutCarriesJsonOnly:
    def test_stdout_is_parseable_json_with_nothing_else(self, runner, stub_client):
        result = runner.invoke(cli.main, ["search", "project=TEST"])
        assert result.stdout.strip() == json.dumps(json.loads(result.stdout), indent=2)

    def test_http_error_leaves_stdout_empty(self, runner, stub_client):
        stub_client.error = JiraHttpError(
            404, "Not Found", "https://jira.example.com/rest/api/3/issue/TEST-1",
            '{"errorMessages":["Issue does not exist"],"errors":{}}',
        )
        result = runner.invoke(cli.main, ["issue", "TEST-1"])
        assert result.stdout == ""

    def test_client_error_leaves_stdout_empty(self, runner, stub_client):
        stub_client.error = ConnectionError("connection refused")
        result = runner.invoke(cli.main, ["search", "project=TEST"])
        assert result.stdout == ""


class TestHttpErrorExitPaths:
    @pytest.mark.parametrize("status", [401, 403, 404])
    def test_status_and_jira_message_on_stderr(self, runner, stub_client, status):
        stub_client.error = JiraHttpError(
            status, "Error", "https://jira.example.com/rest/api/3/search/jql",
            '{"errorMessages":["Issue does not exist"],"errors":{}}',
        )
        result = runner.invoke(cli.main, ["search", "project=TEST"])
        assert result.exit_code == 1
        assert f"HTTP {status}" in result.stderr
        assert "Issue does not exist" in result.stderr
        assert "Traceback" not in result.stderr
        assert "Traceback" not in result.stdout
        assert isinstance(result.exception, SystemExit)

    def test_error_messages_and_field_errors_are_joined(self, runner, stub_client):
        stub_client.error = JiraHttpError(
            400, "Bad Request", "https://jira.example.com/rest/api/3/search/jql",
            '{"errorMessages":["nope"],"errors":{"summary":"is required"}}',
        )
        result = runner.invoke(cli.main, ["search", "project=TEST"])
        assert "nope; summary: is required" in result.stderr

    def test_non_json_body_is_passed_through(self, runner, stub_client):
        stub_client.error = JiraHttpError(
            403, "Forbidden", "https://jira.example.com/rest/api/3/search/jql",
            "<html>proxy denied this endpoint</html>",
        )
        result = runner.invoke(cli.main, ["search", "project=TEST"])
        assert "proxy denied this endpoint" in result.stderr

    def test_unexpected_error_is_one_line(self, runner, stub_client):
        stub_client.error = ConnectionError("connection refused")
        result = runner.invoke(cli.main, ["search", "project=TEST"])
        assert result.exit_code == 1
        assert result.stderr == "error: connection refused\n"


class TestMissingConfigExitPath:
    def test_missing_base_url_exits_2(self, runner, monkeypatch):
        monkeypatch.delenv("JIRA_BASE_URL")
        result = runner.invoke(cli.main, ["me"])
        assert result.exit_code == 2
        assert result.stderr == "error: missing JIRA_BASE_URL\n"
        assert result.stdout == ""

    def test_missing_api_token_exits_2(self, runner, monkeypatch):
        monkeypatch.delenv("JIRA_API_TOKEN")
        result = runner.invoke(cli.main, ["me"])
        assert result.exit_code == 2
        assert result.stderr == "error: missing JIRA_API_TOKEN\n"

    def test_missing_user_email_exits_2(self, runner, monkeypatch):
        monkeypatch.delenv("JIRA_USER_EMAIL")
        result = runner.invoke(cli.main, ["me"])
        assert result.exit_code == 2
        assert result.stderr == "error: missing JIRA_USER_EMAIL\n"

    def test_malformed_basic_auth_exits_2(self, runner, monkeypatch):
        monkeypatch.setenv("JIRA_AUTH_BASIC", base64.b64encode(b"no-separator").decode())
        result = runner.invoke(cli.main, ["me"])
        assert result.exit_code == 2
        assert result.stderr == "error: malformed JIRA_AUTH_BASIC: expected base64 of email:token\n"

    def test_missing_config_never_reaches_the_client(self, runner, monkeypatch):
        monkeypatch.delenv("JIRA_BASE_URL")
        monkeypatch.setattr(cli, "AsyncJiraClient", RecordingClientClass)
        RecordingClientClass.instances.clear()
        runner.invoke(cli.main, ["me"])
        assert RecordingClientClass.instances == []


class TestEnvironmentConfig:
    def test_basic_auth_decodes_to_credentials(self, monkeypatch):
        monkeypatch.setattr(cli, "AsyncJiraClient", RecordingClientClass)
        RecordingClientClass.instances.clear()
        monkeypatch.setenv(
            "JIRA_AUTH_BASIC", base64.b64encode(b"bot@example.com:proxy-token").decode()
        )
        cli.client_from_env()
        client = RecordingClientClass.instances[0]
        assert client.server_url == "https://jira.example.com"
        assert client.user_email == "bot@example.com"
        assert client.api_token == "proxy-token"

    def test_basic_auth_wins_over_token_pair(self, monkeypatch):
        monkeypatch.setattr(cli, "AsyncJiraClient", RecordingClientClass)
        RecordingClientClass.instances.clear()
        monkeypatch.setenv("JIRA_AUTH_BASIC", base64.b64encode(b"bot@example.com:proxy").decode())
        cli.client_from_env()
        assert RecordingClientClass.instances[0].api_token == "proxy"

    def test_token_pair_used_when_basic_auth_absent(self, monkeypatch):
        monkeypatch.setattr(cli, "AsyncJiraClient", RecordingClientClass)
        RecordingClientClass.instances.clear()
        cli.client_from_env()
        client = RecordingClientClass.instances[0]
        assert client.user_email == "user@example.com"
        assert client.api_token == "local-token"

    def test_token_containing_colon_is_kept_whole(self, monkeypatch):
        monkeypatch.setattr(cli, "AsyncJiraClient", RecordingClientClass)
        RecordingClientClass.instances.clear()
        monkeypatch.setenv("JIRA_AUTH_BASIC", base64.b64encode(b"bot@example.com:tok:en").decode())
        cli.client_from_env()
        assert RecordingClientClass.instances[0].api_token == "tok:en"

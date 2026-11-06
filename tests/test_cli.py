"""Tests for the CLI: exit codes, env-var config, output formats, command surface."""

import asyncio
import json

import pytest
from click.testing import CliRunner

from mcp_jira import tools
from mcp_jira.cli import cli
from mcp_jira.client import JiraHttpError


def make_runner():
    """CliRunner that keeps stdout and stderr apart on click 8.1 and 8.2."""
    try:
        return CliRunner(mix_stderr=False)
    except TypeError:  # click >= 8.2 always separates the streams
        return CliRunner()


class StubJiraClient:
    """Duck-typed AsyncJiraClient that records calls and can fail on demand."""

    def __init__(self):
        self.calls = []
        self.closed = False
        self.error = None
        self.result = {
            "issues": [{"key": "TEST-1", "summary": "an issue", "status": "Open"}],
            "total": 1,
        }

    def _record(self, name, **args):
        self.calls.append({"name": name, **args})
        if self.error is not None:
            raise self.error
        return self.result

    async def search_issues(self, jql, max_results=50, start_at=0):
        return self._record("search_issues", jql=jql, max_results=max_results, start_at=start_at)

    async def get_issue(self, issue_key, include_subtasks=False, include_transitions=False):
        return self._record("get_issue", issue_key=issue_key,
                            include_subtasks=include_subtasks,
                            include_transitions=include_transitions)

    async def create_issue(self, project_key, summary, description, issue_type,
                           assignee=None, priority=None, labels=None, custom_fields=None):
        return self._record("create_issue", project_key=project_key, summary=summary,
                            description=description, issue_type=issue_type,
                            assignee=assignee, priority=priority, labels=labels,
                            custom_fields=custom_fields)

    async def update_issue(self, issue_key, summary=None, description=None, assignee=None,
                           priority=None, labels=None, comment=None, custom_fields=None):
        return self._record("update_issue", issue_key=issue_key, summary=summary,
                            description=description, assignee=assignee, priority=priority,
                            labels=labels, comment=comment, custom_fields=custom_fields)

    async def transition_issue(self, issue_key, transition_id, comment=None):
        return self._record("transition_issue", issue_key=issue_key,
                            transition_id=transition_id, comment=comment)

    async def add_comment(self, issue_key, body):
        return self._record("add_comment", issue_key=issue_key, body=body)

    async def get_create_meta(self, project_key, issue_type=None):
        return self._record("get_create_meta", project_key=project_key, issue_type=issue_type)

    async def get_comments(self, issue_key, max_results=50, start_at=0):
        return self._record("get_comments", issue_key=issue_key,
                            max_results=max_results, start_at=start_at)

    async def get_project(self, project_key):
        return self._record("get_project", project_key=project_key)

    async def get_fields(self):
        return self._record("get_fields")

    async def get_myself(self):
        return self._record("get_myself")

    async def close(self):
        self.closed = True


class RecordingClientClass:
    """Stands in for AsyncJiraClient so tests can read its constructor arguments."""

    instances = []

    def __init__(self, server_url, api_token, user_email, max_concurrent_requests=2, **kwargs):
        self.server_url = server_url
        self.api_token = api_token
        self.user_email = user_email
        self.max_concurrent_requests = max_concurrent_requests
        RecordingClientClass.instances.append(self)

    async def close(self):
        pass


@pytest.fixture(autouse=True)
def jira_env(monkeypatch):
    """A complete environment; individual tests remove what they want missing."""
    monkeypatch.setenv("JIRA_SERVER_URL", "https://jira.example.com")
    monkeypatch.setenv("JIRA_USER_EMAIL", "user@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "local-token")
    tools._set_client(None)
    yield
    tools._set_client(None)


@pytest.fixture
def stub_client():
    return StubJiraClient()


@pytest.fixture
def runner():
    return make_runner()


@pytest.fixture
def run(runner, stub_client):
    """Invoke the CLI with the stub client installed for that one call."""

    def _run(argv):
        tools._set_client(stub_client)
        return runner.invoke(cli, argv)

    return _run


ALL_COMMANDS = [
    ["search", "project=TEST"],
    ["issue", "TEST-1"],
    ["create", "TEST", "sum", "desc", "Bug"],
    ["update", "TEST-1", "--summary", "new"],
    ["transition", "TEST-1", "31"],
    ["meta", "TEST"],
    ["comment", "TEST-1", "hello"],
    ["comments", "TEST-1"],
    ["project", "TEST"],
    ["field"],
    ["me"],
]


class TestCommandSurface:
    def test_exposes_the_mcp_tools_and_read_extras(self):
        assert set(cli.commands) == {
            "search", "issue", "create", "update", "transition", "meta",
            "comment", "comments", "project", "field", "me",
        }

    def test_client_is_built_inside_the_event_loop(self, monkeypatch):
        """aiohttp opens its session in the constructor, so it needs a running loop."""
        built = []

        def build(server_url, api_token, user_email, max_concurrent_requests):
            built.append(asyncio.get_running_loop())
            client = StubJiraClient()
            return client

        monkeypatch.setattr(tools, "AsyncJiraClient", build)
        result = make_runner().invoke(cli, ["me"])
        assert result.exit_code == 0
        assert built

    @pytest.mark.parametrize("argv", ALL_COMMANDS)
    def test_every_command_prints_one_json_document(self, run, stub_client, argv):
        result = run(argv)
        assert result.exit_code == 0, result.stderr
        assert json.loads(result.stdout) == stub_client.result
        assert result.stderr == ""
        assert stub_client.closed is True


class TestSearchCommand:
    def test_passes_query_and_paging(self, run, stub_client):
        run(["search", "project=TEST", "--max-results", "5", "--start-at", "10"])
        assert stub_client.calls == [{
            "name": "search_issues", "jql": "project=TEST", "max_results": 5, "start_at": 10,
        }]

    def test_paging_defaults(self, run, stub_client):
        run(["search", "project=TEST"])
        assert stub_client.calls[0]["max_results"] == 50
        assert stub_client.calls[0]["start_at"] == 0


class TestIssueCommand:
    def test_flags_default_to_off(self, run, stub_client):
        run(["issue", "TEST-1"])
        assert stub_client.calls[0]["include_subtasks"] is False
        assert stub_client.calls[0]["include_transitions"] is False

    def test_flags_map_to_client_flags(self, run, stub_client):
        run(["issue", "TEST-1", "--subtasks", "--transitions"])
        assert stub_client.calls[0]["include_subtasks"] is True
        assert stub_client.calls[0]["include_transitions"] is True


class TestCreateCommand:
    def test_passes_required_fields(self, run, stub_client):
        run(["create", "TEST", "a summary", "a description", "Bug"])
        call = stub_client.calls[0]
        assert call["name"] == "create_issue"
        assert call["project_key"] == "TEST"
        assert call["summary"] == "a summary"
        assert call["description"] == "a description"
        assert call["issue_type"] == "Bug"

    def test_repeated_labels_become_a_list(self, run, stub_client):
        run(["create", "TEST", "s", "d", "Bug", "--label", "one", "--label", "two"])
        assert stub_client.calls[0]["labels"] == ["one", "two"]

    def test_optional_fields_absent_by_default(self, run, stub_client):
        run(["create", "TEST", "s", "d", "Bug"])
        call = stub_client.calls[0]
        assert call["labels"] is None
        assert call["assignee"] is None
        assert call["custom_fields"] is None

    def test_field_json_is_parsed(self, run, stub_client):
        run(["create", "TEST", "s", "d", "Bug", "--field", '{"customfield_1": "v"}'])
        assert stub_client.calls[0]["custom_fields"] == {"customfield_1": "v"}

    def test_malformed_field_json_is_a_usage_error(self, run, stub_client):
        result = run(["create", "TEST", "s", "d", "Bug", "--field", "{nope"])
        assert result.exit_code == 2
        assert "expected JSON" in result.stderr
        assert stub_client.calls == []


class TestUpdateCommand:
    def test_refuses_to_run_with_no_changes(self, run, stub_client):
        result = run(["update", "TEST-1"])
        assert result.exit_code == 2
        assert "no changes given" in result.stderr
        assert stub_client.calls == []

    def test_passes_only_the_given_field(self, run, stub_client):
        run(["update", "TEST-1", "--summary", "new"])
        call = stub_client.calls[0]
        assert call["name"] == "update_issue"
        assert call["summary"] == "new"
        assert call["description"] is None
        assert call["comment"] is None

    def test_comment_alone_is_enough(self, run, stub_client):
        run(["update", "TEST-1", "--comment", "a note"])
        assert stub_client.calls[0]["comment"] == "a note"


class TestTransitionCommand:
    def test_passes_id_and_comment(self, run, stub_client):
        run(["transition", "TEST-1", "31", "--comment", "done"])
        assert stub_client.calls[0] == {
            "name": "transition_issue", "issue_key": "TEST-1",
            "transition_id": "31", "comment": "done",
        }


class TestCommentCommand:
    def test_passes_body(self, run, stub_client):
        run(["comment", "TEST-1", "hello"])
        assert stub_client.calls[0] == {
            "name": "add_comment", "issue_key": "TEST-1", "body": "hello",
        }


class TestMetaCommand:
    def test_lists_types_without_issue_type(self, run, stub_client):
        run(["meta", "TEST"])
        assert stub_client.calls[0] == {
            "name": "get_create_meta", "project_key": "TEST", "issue_type": None,
        }

    def test_passes_issue_type(self, run, stub_client):
        run(["meta", "TEST", "--issue-type", "Bug"])
        assert stub_client.calls[0]["issue_type"] == "Bug"


class TestCommentsCommand:
    def test_passes_paging_options(self, run, stub_client):
        run(["comments", "TEST-1", "--max-results", "2", "--start-at", "4"])
        assert stub_client.calls == [{
            "name": "get_comments", "issue_key": "TEST-1", "max_results": 2, "start_at": 4,
        }]


class TestReadExtras:
    def test_project(self, run, stub_client):
        run(["project", "TEST"])
        assert stub_client.calls[0] == {"name": "get_project", "project_key": "TEST"}

    def test_field(self, run, stub_client):
        run(["field"])
        assert stub_client.calls[0] == {"name": "get_fields"}

    def test_me(self, run, stub_client):
        run(["me"])
        assert stub_client.calls[0] == {"name": "get_myself"}


class TestOutputFormats:
    def test_json_is_the_default_and_is_one_document(self, run, stub_client):
        result = run(["search", "project=TEST"])
        assert result.stdout.strip() == json.dumps(stub_client.result, indent=2, ensure_ascii=False)

    def test_table_renders_the_result_list(self, run):
        result = run(["search", "project=TEST", "-o", "table"])
        assert "key" in result.stdout and "summary" in result.stdout
        assert "TEST-1" in result.stdout
        assert "|" not in result.stdout

    def test_md_renders_a_markdown_table(self, run):
        result = run(["search", "project=TEST", "-o", "md"])
        assert "### issues" in result.stdout
        assert "| key |" in result.stdout
        assert "| --- |" in result.stdout
        assert "TEST-1" in result.stdout

    def test_table_truncates_long_cells(self, run, stub_client):
        stub_client.result = {"issues": [{"key": "TEST-1", "summary": "x" * 200}]}
        result = run(["search", "project=TEST", "-o", "table"])
        assert "x" * 200 not in result.stdout
        assert "..." in result.stdout

    def test_table_never_emits_json(self, run, stub_client):
        result = run(["search", "project=TEST", "-o", "table"])
        with pytest.raises(ValueError):
            json.loads(result.stdout)


class TestStdoutCarriesJsonOnly:
    def test_http_error_leaves_stdout_empty(self, run, stub_client):
        stub_client.error = JiraHttpError(
            404, "Not Found", "https://jira.example.com/rest/api/3/issue/TEST-1",
            '{"errorMessages":["Issue does not exist"],"errors":{}}',
        )
        result = run(["issue", "TEST-1"])
        assert result.stdout == ""

    def test_client_error_leaves_stdout_empty(self, run, stub_client):
        stub_client.error = ConnectionError("connection refused")
        result = run(["search", "project=TEST"])
        assert result.stdout == ""


class TestHttpErrorExitPaths:
    @pytest.mark.parametrize("status", [401, 403, 404])
    def test_status_and_jira_message_on_stderr(self, run, stub_client, status):
        stub_client.error = JiraHttpError(
            status, "Error", "https://jira.example.com/rest/api/3/search/jql",
            '{"errorMessages":["Issue does not exist"],"errors":{}}',
        )
        result = run(["search", "project=TEST"])
        assert result.exit_code == 1
        assert f"HTTP {status}" in result.stderr
        assert "Issue does not exist" in result.stderr
        assert "Traceback" not in result.stderr
        assert isinstance(result.exception, SystemExit)

    def test_error_messages_and_field_errors_are_joined(self, run, stub_client):
        stub_client.error = JiraHttpError(
            400, "Bad Request", "https://jira.example.com/rest/api/3/search/jql",
            '{"errorMessages":["nope"],"errors":{"summary":"is required"}}',
        )
        result = run(["search", "project=TEST"])
        assert "nope; summary: is required" in result.stderr

    def test_non_json_body_is_passed_through(self, run, stub_client):
        stub_client.error = JiraHttpError(
            403, "Forbidden", "https://jira.example.com/rest/api/3/search/jql",
            "<html>access denied</html>",
        )
        result = run(["search", "project=TEST"])
        assert "access denied" in result.stderr

    def test_unexpected_error_is_one_line(self, run, stub_client):
        stub_client.error = ConnectionError("connection refused")
        result = run(["search", "project=TEST"])
        assert result.exit_code == 1
        assert result.stderr == "error: connection refused\n"


class TestMissingConfigExitPath:
    @pytest.mark.parametrize("missing", ["JIRA_SERVER_URL", "JIRA_API_TOKEN", "JIRA_USER_EMAIL"])
    def test_missing_variable_exits_2_and_names_it(self, runner, monkeypatch, missing):
        monkeypatch.delenv(missing)
        result = runner.invoke(cli, ["me"])
        assert result.exit_code == 2
        assert missing in result.stderr
        assert result.stdout == ""

    def test_missing_config_never_reaches_the_client(self, runner, monkeypatch):
        monkeypatch.delenv("JIRA_SERVER_URL")
        monkeypatch.setattr(tools, "AsyncJiraClient", RecordingClientClass)
        RecordingClientClass.instances.clear()
        runner.invoke(cli, ["me"])
        assert RecordingClientClass.instances == []


class TestEnvironmentConfig:
    def test_client_receives_the_three_variables(self, monkeypatch):
        monkeypatch.setattr(tools, "AsyncJiraClient", RecordingClientClass)
        RecordingClientClass.instances.clear()
        asyncio.run(tools.get_client())
        client = RecordingClientClass.instances[0]
        assert client.server_url == "https://jira.example.com"
        assert client.api_token == "local-token"
        assert client.user_email == "user@example.com"

    def test_token_containing_colon_is_kept_whole(self, monkeypatch):
        monkeypatch.setenv("JIRA_API_TOKEN", "tok:en")
        monkeypatch.setattr(tools, "AsyncJiraClient", RecordingClientClass)
        RecordingClientClass.instances.clear()
        asyncio.run(tools.get_client())
        assert RecordingClientClass.instances[0].api_token == "tok:en"

    def test_concurrency_setting_is_read(self, monkeypatch):
        monkeypatch.setenv("MAX_CONCURRENT_REQUESTS", "7")
        monkeypatch.setattr(tools, "AsyncJiraClient", RecordingClientClass)
        RecordingClientClass.instances.clear()
        asyncio.run(tools.get_client())
        assert RecordingClientClass.instances[0].max_concurrent_requests == 7


class TestNonTabularRenderPaths:
    """`jira me`, `jira project`, `jira field` return flat dicts, not a list of
    rows. Those results take _print_dict / _md_dict instead of _print_table, and
    the difference is what a user sees for three of the eleven commands."""

    def test_table_renders_a_flat_dict_without_a_table(self, run, stub_client):
        stub_client.result = {"display_name": "Jude Zhu", "email": "judzhu@redhat.com"}
        result = run(["me", "-o", "table"])
        assert result.exit_code == 0
        assert "display_name: Jude Zhu" in result.stdout

    def test_md_renders_a_flat_dict_as_bold_keys(self, run, stub_client):
        stub_client.result = {"display_name": "Jude Zhu"}
        result = run(["me", "-o", "md"])
        assert result.exit_code == 0
        assert "**display_name:** Jude Zhu" in result.stdout

    def test_empty_search_in_table_mode_exits_cleanly(self, run, stub_client):
        stub_client.result = {"issues": [], "total": 0}
        result = run(["search", "project=NONE", "-o", "table"])
        assert result.exit_code == 0
        with pytest.raises(ValueError):
            json.loads(result.stdout)

    def test_table_falls_back_to_key_value_when_no_list_is_tabular(self, run, stub_client):
        stub_client.result = {"project": "TEST", "lead": None, "labels": ["a", "b"]}
        result = run(["project", "TEST", "-o", "table"])
        assert "project: TEST" in result.stdout

    def test_none_renders_as_empty_not_the_word_none(self, run, stub_client):
        stub_client.result = {"project": "TEST", "lead": None}
        result = run(["project", "TEST", "-o", "table"])
        assert "None" not in result.stdout

    def test_list_values_are_comma_joined_not_repr(self, run, stub_client):
        stub_client.result = {"project": "TEST", "labels": ["a", "b"]}
        result = run(["project", "TEST", "-o", "table"])
        assert "a, b" in result.stdout
        assert "['a'" not in result.stdout


class TestErrorBodyShapes:
    """JIRA's error body is not always the documented object."""

    def test_non_object_json_body_falls_back_to_the_raw_body(self, run, stub_client):
        stub_client.error = JiraHttpError(400, "Bad Request", "/rest/api/3/issue", '["a problem"]')
        result = run(["issue", "TEST-1"])
        assert result.exit_code == 1
        assert "a problem" in result.stderr


class TestHelpSurface:
    def test_epilog_is_printed_with_help(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert "Command Details:" in result.stdout

    def test_required_env_vars_are_named_in_help(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert "JIRA_USER_EMAIL" in result.stdout

    def test_nested_dict_renders_indented_in_table_mode(self, run, stub_client):
        stub_client.result = {"project": "TEST", "lead": {"name": "Jude", "active": True}}
        result = run(["project", "TEST", "-o", "table"])
        assert "lead:" in result.stdout
        assert "name: Jude" in result.stdout

    def test_nested_dict_renders_as_bullets_in_md_mode(self, run, stub_client):
        stub_client.result = {"project": "TEST", "lead": {"name": "Jude"}}
        result = run(["project", "TEST", "-o", "md"])
        assert "- name: Jude" in result.stdout

    def test_scalar_list_renders_comma_joined_in_md_mode(self, run, stub_client):
        stub_client.result = {"project": "TEST", "labels": ["a", "b"]}
        result = run(["project", "TEST", "-o", "md"])
        assert "**labels:** a, b" in result.stdout

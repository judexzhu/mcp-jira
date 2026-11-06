"""Tests for the MCP entry point: tool surface, prompts, logging, and startup.

The registered tool names are a compatibility contract. Existing MCP client
configs and saved prompts refer to `jira_*`, so they are asserted by name —
a rename here silently breaks every configured client.
"""

import pytest

from jira_mcp_server import main as shim_main
from mcp_jira import server, tools


EXPECTED_TOOLS = {
    "jira_search_issues": "search_issues",
    "jira_get_issue": "get_issue",
    "jira_create_issue": "create_issue",
    "jira_update_issue": "update_issue",
    "jira_transition_issue": "transition_issue",
    "jira_link_issues": "link_issues",
    "jira_add_remote_link": "add_remote_link",
    "jira_get_create_meta": "get_create_meta",
}


@pytest.fixture
def mcp():
    return server.mcp


class TestToolSurface:
    async def test_registers_exactly_the_expected_names(self, mcp):
        names = {tool.name for tool in await mcp.list_tools()}
        assert names == set(EXPECTED_TOOLS)

    @pytest.mark.parametrize("tool_name,operation", sorted(EXPECTED_TOOLS.items()))
    async def test_tool_binds_the_shared_operation(self, mcp, tool_name, operation):
        """Each tool must be the CLI's operation, not a copy that can drift.

        Reaches into the tool manager because the public MCPTool model exposes
        only the schema, not the bound function. Identity is the assertion that
        matters: a wrapper here would let server and CLI diverge silently.
        """
        bound = mcp._tool_manager._tools[tool_name].fn
        assert bound is getattr(tools, operation)

    async def test_no_tool_escaped_the_jira_prefix(self, mcp):
        for tool in await mcp.list_tools():
            assert tool.name.startswith("jira_"), tool.name


class TestPrompts:
    async def test_registers_both_prompts(self, mcp):
        names = {prompt.name for prompt in await mcp.list_prompts()}
        assert names == {"my_open_issues", "my_watched_issues"}

    async def test_open_issues_prompt_text(self, mcp):
        result = await mcp.get_prompt("my_open_issues")
        assert "assignee = currentUser()" in result.messages[0].content.text

    async def test_watched_issues_defaults_to_seven_days(self, mcp):
        result = await mcp.get_prompt("my_watched_issues")
        assert "updated >= -7d" in result.messages[0].content.text

    async def test_watched_issues_honours_days_argument(self, mcp):
        result = await mcp.get_prompt("my_watched_issues", {"days": 30})
        assert "updated >= -30d" in result.messages[0].content.text


class TestSetupLogging:
    """setup_logging delegates to basicConfig, which is a no-op once the root
    logger has handlers. Capture the call rather than inspecting the root
    logger, which would only ever show the import-time configuration.
    """

    @staticmethod
    def _capture(monkeypatch):
        import logging

        captured = {}
        monkeypatch.setattr(
            logging, "basicConfig", lambda **kwargs: captured.update(kwargs)
        )
        return captured

    def test_default_level_is_error(self, monkeypatch):
        import logging

        monkeypatch.delenv("LOG_LEVEL", raising=False)
        captured = self._capture(monkeypatch)

        server.setup_logging()

        assert captured["level"] == logging.ERROR

    def test_rejects_bad_level_by_uppercasing_it(self, monkeypatch):
        import logging

        monkeypatch.setenv("LOG_LEVEL", "debug")
        captured = self._capture(monkeypatch)

        server.setup_logging()

        assert captured["level"] == logging.DEBUG

    def test_logs_to_file_only_by_default(self, monkeypatch):
        import logging

        monkeypatch.delenv("LOG_TO_STDOUT", raising=False)
        captured = self._capture(monkeypatch)

        server.setup_logging()

        handlers = captured["handlers"]
        assert len(handlers) == 1
        assert isinstance(handlers[0], logging.FileHandler)

    def test_adds_stdout_handler_when_opted_in(self, monkeypatch):
        import logging
        import sys

        monkeypatch.setenv("LOG_TO_STDOUT", "true")
        captured = self._capture(monkeypatch)

        server.setup_logging()

        streams = [
            h for h in captured["handlers"]
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        assert len(streams) == 1, "stdout logging is opt-in because it corrupts stdio MCP"
        assert streams[0].stream is sys.stdout

    def test_quiets_noisy_aiohttp_loggers(self, monkeypatch):
        import logging

        self._capture(monkeypatch)
        server.setup_logging()

        assert logging.getLogger("aiohttp").level == logging.WARNING


class TestMain:
    def test_exits_1_and_names_every_missing_variable(self, monkeypatch):
        for var in ("JIRA_SERVER_URL", "JIRA_API_TOKEN", "JIRA_USER_EMAIL"):
            monkeypatch.delenv(var, raising=False)

        with pytest.raises(SystemExit) as exit_info:
            server.main()

        assert exit_info.value.code == 1

    def test_names_only_the_variable_that_is_missing(self, monkeypatch, caplog):
        monkeypatch.setenv("JIRA_SERVER_URL", "https://redhat.atlassian.net")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        monkeypatch.delenv("JIRA_USER_EMAIL", raising=False)

        with pytest.raises(SystemExit):
            server.main()

        assert any(
            "JIRA_USER_EMAIL" in record.getMessage() for record in caplog.records
        )

    def test_runs_stdio_transport_when_configured(self, monkeypatch):
        monkeypatch.setenv("JIRA_SERVER_URL", "https://redhat.atlassian.net")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        monkeypatch.setenv("JIRA_USER_EMAIL", "a@redhat.com")

        called = {}
        monkeypatch.setattr(server.mcp, "run", lambda transport: called.update(t=transport))

        server.main()

        assert called["t"] == "stdio", "stdio is the only transport an MCP client can spawn"


class TestRootShim:
    def test_shim_reexports_the_same_objects(self):
        """Old client configs invoke jira_mcp_server.py, which must not diverge."""
        assert shim_main is server.main


class TestSingleSourceOfTruth:
    """ADR-0002 promises the two entry points cannot drift. The required-env
    list is the one piece of configuration both still check themselves, so it
    gets its own guard: adding a required variable in one place must be visible
    in the other without a second edit."""

    def test_server_checks_the_same_variable_list_as_the_client(self, monkeypatch, caplog):
        monkeypatch.setenv("JIRA_SERVER_URL", "https://redhat.atlassian.net")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        monkeypatch.setenv("JIRA_USER_EMAIL", "a@redhat.com")
        # A fourth requirement introduced in the operations layer only.
        monkeypatch.setattr(tools, "REQUIRED_ENV", (*tools.REQUIRED_ENV, "JIRA_EXTRA"))

        with pytest.raises(SystemExit) as exit_info:
            server.main()

        assert exit_info.value.code == 1
        assert any("JIRA_EXTRA" in record.getMessage() for record in caplog.records), (
            "server.main enforced its own list instead of the operations layer's"
        )

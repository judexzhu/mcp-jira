"""Tests for MCP tool functions using a FakeJiraClient."""

import pytest

from jira_client import JiraClientProtocol
from jira_mcp_server import (
    _set_client,
    jira_search_issues,
    jira_get_issue,
    jira_create_issue,
    jira_update_issue,
    jira_transition_issue,
    jira_get_create_meta,
)


class FakeJiraClient:
    """In-memory JIRA client for testing."""

    def __init__(self):
        self.is_cloud = False
        self.issues = {
            "TEST-1": {
                "key": "TEST-1",
                "summary": "Test issue",
                "status": "Open",
                "type": "Bug",
            },
            "TEST-2": {
                "key": "TEST-2",
                "summary": "Another issue",
                "status": "Done",
                "type": "Task",
            },
        }
        self.comments = {
            "TEST-1": [
                {"author": "Jude", "body": "first comment", "created": "2025-01-01"},
            ],
        }
        self.created_issues = []
        self.updates = []
        self.transitions = []

    async def search_issues(self, jql, max_results=50, start_at=0):
        all_issues = list(self.issues.values())
        page = all_issues[start_at:start_at + max_results]
        return {
            "issues": page,
            "total": len(all_issues),
            "start_at": start_at,
            "max_results": max_results,
        }

    async def get_issue(self, issue_key, include_subtasks=False, include_transitions=False):
        if issue_key not in self.issues:
            raise Exception(f"Issue {issue_key} not found")
        result = dict(self.issues[issue_key])
        if issue_key in self.comments:
            result["comments"] = self.comments[issue_key]
        if include_subtasks:
            result["subtasks"] = [{"key": f"{issue_key}-1", "summary": "Subtask"}]
        if include_transitions:
            result["transitions"] = [{"id": "31", "name": "Done", "to": "Done"}]
        return result

    async def create_issue(self, project_key, summary, description, issue_type,
                           assignee=None, priority=None, labels=None, custom_fields=None):
        key = f"{project_key}-{len(self.created_issues) + 100}"
        self.created_issues.append({"key": key, "summary": summary})
        return {"key": key}

    async def update_issue(self, issue_key, summary=None, description=None,
                           assignee=None, priority=None, labels=None,
                           comment=None, custom_fields=None):
        self.updates.append({
            "key": issue_key, "summary": summary, "description": description,
            "assignee": assignee, "priority": priority, "labels": labels,
            "comment": comment, "custom_fields": custom_fields,
        })
        return {"key": issue_key, "updated": True}

    async def transition_issue(self, issue_key, transition_id, comment=None):
        self.transitions.append({"key": issue_key, "id": transition_id, "comment": comment})
        return {"key": issue_key, "transitioned": True, "transition_id": transition_id}

    async def get_create_meta(self, project_key, issue_type=None):
        types = [
            {"id": "10016", "name": "Bug", "subtask": False},
            {"id": "10017", "name": "Task", "subtask": False},
        ]
        if issue_type is None:
            return {"project": project_key, "issue_types": types}
        return {
            "project": project_key,
            "issue_type": issue_type,
            "fields": [
                {"key": "summary", "name": "Summary", "required": True},
                {"key": "priority", "name": "Priority", "required": False, "allowed": ["High", "Medium", "Low"]},
            ]
        }

    async def close(self):
        pass


class TestProtocolConformance:
    def test_fake_client_satisfies_protocol(self):
        assert isinstance(FakeJiraClient(), JiraClientProtocol)


@pytest.fixture(autouse=True)
def fake_client():
    """Inject FakeJiraClient before each test, reset after."""
    client = FakeJiraClient()
    _set_client(client)
    yield client
    _set_client(None)


class TestSearchIssues:
    async def test_returns_paginated_result(self, fake_client):
        result = await jira_search_issues("project=TEST")
        assert "issues" in result
        assert "total" in result
        assert result["total"] == 2
        assert len(result["issues"]) == 2

    async def test_respects_max_results(self, fake_client):
        result = await jira_search_issues("project=TEST", max_results=1)
        assert len(result["issues"]) == 1
        assert result["total"] == 2

    async def test_start_at(self, fake_client):
        result = await jira_search_issues("project=TEST", start_at=1)
        assert result["start_at"] == 1
        assert len(result["issues"]) == 1

    async def test_pagination_metadata(self, fake_client):
        result = await jira_search_issues("project=TEST", max_results=1, start_at=0)
        assert result["max_results"] == 1
        assert result["start_at"] == 0
        assert result["total"] == 2


class TestGetIssue:
    async def test_returns_issue(self, fake_client):
        result = await jira_get_issue("TEST-1")
        assert result["key"] == "TEST-1"
        assert result["summary"] == "Test issue"

    async def test_includes_comments(self, fake_client):
        result = await jira_get_issue("TEST-1")
        assert result["comments"][0]["body"] == "first comment"

    async def test_not_found_raises(self, fake_client):
        with pytest.raises(Exception, match="not found"):
            await jira_get_issue("NOPE-999")

    async def test_include_subtasks(self, fake_client):
        result = await jira_get_issue("TEST-1", include_subtasks=True)
        assert "subtasks" in result

    async def test_without_subtasks(self, fake_client):
        result = await jira_get_issue("TEST-1")
        assert "subtasks" not in result

    async def test_include_transitions(self, fake_client):
        result = await jira_get_issue("TEST-1", include_transitions=True)
        assert "transitions" in result

    async def test_without_transitions(self, fake_client):
        result = await jira_get_issue("TEST-1")
        assert "transitions" not in result

    async def test_both_flags(self, fake_client):
        result = await jira_get_issue("TEST-1", include_subtasks=True, include_transitions=True)
        assert "subtasks" in result
        assert "transitions" in result


class TestCreateIssue:
    async def test_creates_issue(self, fake_client):
        result = await jira_create_issue("TEST", "New bug", "Description", "Bug")
        assert result["key"].startswith("TEST-")
        assert len(fake_client.created_issues) == 1

    async def test_with_optional_fields(self, fake_client):
        result = await jira_create_issue(
            "TEST", "Task", "Do stuff", "Task",
            assignee_name="jude", priority_name="High", labels=["urgent"],
        )
        assert result["key"].startswith("TEST-")


class TestUpdateIssue:
    async def test_update_summary(self, fake_client):
        result = await jira_update_issue("TEST-1", summary="New summary")
        assert result["updated"] is True
        assert fake_client.updates[0]["summary"] == "New summary"

    async def test_update_with_comment(self, fake_client):
        result = await jira_update_issue("TEST-1", summary="Updated", comment="why I changed it")
        assert fake_client.updates[0]["comment"] == "why I changed it"

    async def test_comment_only(self, fake_client):
        result = await jira_update_issue("TEST-1", comment="just a comment")
        assert fake_client.updates[0]["summary"] is None
        assert fake_client.updates[0]["comment"] == "just a comment"

    async def test_update_multiple_fields(self, fake_client):
        result = await jira_update_issue("TEST-1", summary="New", priority="High", labels=["a", "b"])
        update = fake_client.updates[0]
        assert update["summary"] == "New"
        assert update["priority"] == "High"
        assert update["labels"] == ["a", "b"]

    async def test_passes_assignee(self, fake_client):
        await jira_update_issue("TEST-1", assignee="jsmith")
        assert fake_client.updates[0]["assignee"] == "jsmith"

    async def test_passes_description(self, fake_client):
        await jira_update_issue("TEST-1", description="new desc")
        assert fake_client.updates[0]["description"] == "new desc"

    async def test_passes_custom_fields(self, fake_client):
        await jira_update_issue("TEST-1", custom_fields={"customfield_10001": "val"})
        assert fake_client.updates[0]["custom_fields"] == {"customfield_10001": "val"}


class TestTransitionIssue:
    async def test_transition(self, fake_client):
        result = await jira_transition_issue("TEST-1", "31")
        assert result["transitioned"] is True
        assert fake_client.transitions[0]["id"] == "31"

    async def test_transition_with_comment(self, fake_client):
        await jira_transition_issue("TEST-1", "31", comment="closing this")
        assert fake_client.transitions[0]["comment"] == "closing this"

    async def test_transition_without_comment(self, fake_client):
        await jira_transition_issue("TEST-1", "31")
        assert fake_client.transitions[0]["comment"] is None

    async def test_transition_returns_id(self, fake_client):
        result = await jira_transition_issue("TEST-1", "31")
        assert result["transition_id"] == "31"


class TestGetCreateMeta:
    async def test_list_issue_types(self, fake_client):
        result = await jira_get_create_meta("TEST")
        assert result["project"] == "TEST"
        assert len(result["issue_types"]) == 2
        assert result["issue_types"][0]["name"] == "Bug"

    async def test_get_fields_for_type(self, fake_client):
        result = await jira_get_create_meta("TEST", issue_type="Bug")
        assert result["issue_type"] == "Bug"
        assert len(result["fields"]) == 2
        assert result["fields"][0]["name"] == "Summary"
        assert result["fields"][0]["required"] is True

    async def test_fields_include_allowed_values(self, fake_client):
        result = await jira_get_create_meta("TEST", issue_type="Bug")
        priority_field = next(f for f in result["fields"] if f["key"] == "priority")
        assert priority_field["allowed"] == ["High", "Medium", "Low"]


class TestErrorPropagation:
    async def test_error_propagates_from_client(self, fake_client):
        async def failing_search(*args, **kwargs):
            raise ConnectionError("Network error")

        fake_client.search_issues = failing_search
        with pytest.raises(ConnectionError, match="Network error"):
            await jira_search_issues("project=TEST")

"""Tests for AsyncJiraClient with mocked HTTP."""

import pytest
import aiohttp
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from jira_client import AsyncJiraClient, JiraHttpError


@pytest.fixture
async def cloud_client():
    client = AsyncJiraClient("https://redhat.atlassian.net", "tok", user_email="a@redhat.com")
    yield client
    await client.close()


@pytest.fixture
async def server_client():
    client = AsyncJiraClient("https://jira.corp.com", "tok")
    yield client
    await client.close()


class TestApiPrefix:
    async def test_cloud_uses_v3(self, cloud_client):
        assert cloud_client._fmt.api_prefix == "/rest/api/3"
        assert cloud_client.is_cloud is True

    async def test_server_uses_v2(self, server_client):
        assert server_client._fmt.api_prefix == "/rest/api/2"
        assert server_client.is_cloud is False


class TestSearchEndpoint:
    async def test_cloud_search_endpoint(self, cloud_client):
        with patch.object(cloud_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"issues": [], "total": 0}
            await cloud_client.search_issues("project=TEST")
            endpoint = mock_req.call_args[0][1]
            assert endpoint == "/rest/api/3/search/jql"

    async def test_server_search_endpoint(self, server_client):
        with patch.object(server_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"issues": [], "total": 0}
            await server_client.search_issues("project=TEST")
            endpoint = mock_req.call_args[0][1]
            assert endpoint == "/rest/api/2/search"

    async def test_returns_pagination_metadata(self, server_client):
        with patch.object(server_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"issues": [], "total": 100}
            result = await server_client.search_issues("project=TEST", max_results=10, start_at=20)
            assert result["total"] == 100
            assert result["start_at"] == 20
            assert result["max_results"] == 10

    async def test_passes_start_at_param(self, server_client):
        with patch.object(server_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"issues": [], "total": 0}
            await server_client.search_issues("project=TEST", start_at=50)
            params = mock_req.call_args[1]["params"]
            assert params["startAt"] == 50


class TestGetIssueEndpoint:
    async def test_cloud_get_issue(self, cloud_client):
        with patch.object(cloud_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"key": "TEST-1", "fields": {"summary": "x"}}
            await cloud_client.get_issue("TEST-1")
            endpoint = mock_req.call_args[0][1]
            assert endpoint == "/rest/api/3/issue/TEST-1"

    async def test_server_get_issue(self, server_client):
        with patch.object(server_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"key": "TEST-1", "fields": {"summary": "x"}}
            await server_client.get_issue("TEST-1")
            endpoint = mock_req.call_args[0][1]
            assert endpoint == "/rest/api/2/issue/TEST-1"


class TestCreateIssueCloudVsServer:
    async def test_cloud_uses_account_id_assignee(self, cloud_client):
        with patch.object(cloud_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"key": "TEST-1"}
            await cloud_client.create_issue("TEST", "sum", "desc", "Bug", assignee="acc123")
            payload = mock_req.call_args[1]["json"]
            assert payload["fields"]["assignee"] == {"accountId": "acc123"}

    async def test_server_uses_name_assignee(self, server_client):
        with patch.object(server_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"key": "TEST-1"}
            await server_client.create_issue("TEST", "sum", "desc", "Bug", assignee="jsmith")
            payload = mock_req.call_args[1]["json"]
            assert payload["fields"]["assignee"] == {"name": "jsmith"}

    async def test_cloud_wraps_description_in_adf(self, cloud_client):
        with patch.object(cloud_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"key": "TEST-1"}
            await cloud_client.create_issue("TEST", "sum", "my description", "Bug")
            payload = mock_req.call_args[1]["json"]
            desc = payload["fields"]["description"]
            assert desc["type"] == "doc"
            assert desc["version"] == 1
            assert desc["content"][0]["content"][0]["text"] == "my description"

    async def test_server_sends_plain_description(self, server_client):
        with patch.object(server_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"key": "TEST-1"}
            await server_client.create_issue("TEST", "sum", "my description", "Bug")
            payload = mock_req.call_args[1]["json"]
            assert payload["fields"]["description"] == "my description"

    async def test_cloud_create_endpoint(self, cloud_client):
        with patch.object(cloud_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"key": "TEST-1"}
            await cloud_client.create_issue("TEST", "sum", "desc", "Bug")
            endpoint = mock_req.call_args[0][1]
            assert endpoint == "/rest/api/3/issue"

    async def test_server_create_endpoint(self, server_client):
        with patch.object(server_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"key": "TEST-1"}
            await server_client.create_issue("TEST", "sum", "desc", "Bug")
            endpoint = mock_req.call_args[0][1]
            assert endpoint == "/rest/api/2/issue"

    async def test_create_with_optional_fields(self, server_client):
        with patch.object(server_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"key": "TEST-1"}
            await server_client.create_issue(
                "TEST", "sum", "desc", "Bug",
                priority="High", labels=["urgent"],
                custom_fields={"customfield_10001": "val"}
            )
            payload = mock_req.call_args[1]["json"]
            assert payload["fields"]["priority"] == {"name": "High"}
            assert payload["fields"]["labels"] == ["urgent"]
            assert payload["fields"]["customfield_10001"] == "val"


class TestAddCommentCloudVsServer:
    async def test_cloud_wraps_body_in_adf(self, cloud_client):
        with patch.object(cloud_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {
                "author": {"displayName": "Jude"},
                "body": {"type": "doc", "content": []},
                "created": "2025-01-01",
            }
            await cloud_client.add_comment("TEST-1", "hello world")
            payload = mock_req.call_args[1]["json"]
            assert payload["body"]["type"] == "doc"
            assert payload["body"]["content"][0]["content"][0]["text"] == "hello world"

    async def test_server_sends_plain_body(self, server_client):
        with patch.object(server_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {
                "author": {"displayName": "Jude"},
                "body": "hello world",
                "created": "2025-01-01",
            }
            await server_client.add_comment("TEST-1", "hello world")
            payload = mock_req.call_args[1]["json"]
            assert payload["body"] == "hello world"

    async def test_cloud_comment_endpoint(self, cloud_client):
        with patch.object(cloud_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {
                "author": {"displayName": "Jude"},
                "body": {},
                "created": "2025-01-01",
            }
            await cloud_client.add_comment("TEST-1", "text")
            endpoint = mock_req.call_args[0][1]
            assert endpoint == "/rest/api/3/issue/TEST-1/comment"


class TestGetIssueFlags:
    async def test_include_subtasks_extra_call(self, cloud_client):
        call_log = []

        async def mock_req(method, endpoint, **kwargs):
            call_log.append(endpoint)
            if 'subtasks' in kwargs.get('params', {}).get('fields', ''):
                return {"key": "TEST-1", "fields": {"subtasks": [
                    {"key": "TEST-1-1", "fields": {"summary": "sub"}}
                ]}}
            return {"key": "TEST-1", "fields": {"summary": "x"}}

        with patch.object(cloud_client, '_make_request', side_effect=mock_req):
            result = await cloud_client.get_issue("TEST-1", include_subtasks=True)
            assert "subtasks" in result
            assert len(call_log) == 2

    async def test_include_transitions_extra_call(self, cloud_client):
        call_log = []

        async def mock_req(method, endpoint, **kwargs):
            call_log.append(endpoint)
            if 'transitions' in endpoint:
                return {"transitions": [{"id": "31", "name": "Done", "to": {"name": "Done"}}]}
            return {"key": "TEST-1", "fields": {"summary": "x"}}

        with patch.object(cloud_client, '_make_request', side_effect=mock_req):
            result = await cloud_client.get_issue("TEST-1", include_transitions=True)
            assert "transitions" in result
            assert result["transitions"][0]["name"] == "Done"
            assert len(call_log) == 2

    async def test_no_flags_single_call(self, cloud_client):
        call_log = []

        async def mock_req(method, endpoint, **kwargs):
            call_log.append(endpoint)
            return {"key": "TEST-1", "fields": {"summary": "x"}}

        with patch.object(cloud_client, '_make_request', side_effect=mock_req):
            await cloud_client.get_issue("TEST-1")
            assert len(call_log) == 1


class TestUpdateIssue:
    async def test_update_endpoint(self, cloud_client):
        with patch.object(cloud_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await cloud_client.update_issue("TEST-1", summary="new")
            assert mock_req.call_args[0][0] == "PUT"
            assert mock_req.call_args[0][1] == "/rest/api/3/issue/TEST-1"

    async def test_update_sends_summary(self, server_client):
        with patch.object(server_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await server_client.update_issue("TEST-1", summary="new")
            payload = mock_req.call_args[1]["json"]
            assert payload == {"fields": {"summary": "new"}}

    async def test_cloud_adf_description(self, cloud_client):
        with patch.object(cloud_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await cloud_client.update_issue("TEST-1", description="new desc")
            payload = mock_req.call_args[1]["json"]
            assert payload["fields"]["description"]["type"] == "doc"

    async def test_server_plain_description(self, server_client):
        with patch.object(server_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await server_client.update_issue("TEST-1", description="new desc")
            payload = mock_req.call_args[1]["json"]
            assert payload["fields"]["description"] == "new desc"

    async def test_cloud_account_id_assignee(self, cloud_client):
        with patch.object(cloud_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await cloud_client.update_issue("TEST-1", assignee="acc123")
            payload = mock_req.call_args[1]["json"]
            assert payload["fields"]["assignee"] == {"accountId": "acc123"}

    async def test_server_name_assignee(self, server_client):
        with patch.object(server_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await server_client.update_issue("TEST-1", assignee="jsmith")
            payload = mock_req.call_args[1]["json"]
            assert payload["fields"]["assignee"] == {"name": "jsmith"}

    async def test_update_with_comment(self, server_client):
        calls = []

        async def mock_req(method, endpoint, **kwargs):
            calls.append((method, endpoint))
            if method == "POST":
                return {"author": {"displayName": "x"}, "body": "c", "created": "2025-01-01"}
            return {}

        with patch.object(server_client, '_make_request', side_effect=mock_req):
            await server_client.update_issue("TEST-1", summary="x", comment="reason")
            assert calls[0] == ("PUT", "/rest/api/2/issue/TEST-1")
            assert calls[1] == ("POST", "/rest/api/2/issue/TEST-1/comment")

    async def test_comment_only_no_put(self, server_client):
        calls = []

        async def mock_req(method, endpoint, **kwargs):
            calls.append(method)
            return {"author": {"displayName": "x"}, "body": "c", "created": "2025-01-01"}

        with patch.object(server_client, '_make_request', side_effect=mock_req):
            await server_client.update_issue("TEST-1", comment="just a note")
            assert "PUT" not in calls
            assert "POST" in calls


class TestTransitionIssue:
    async def test_transition_endpoint(self, cloud_client):
        with patch.object(cloud_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await cloud_client.transition_issue("TEST-1", "31")
            assert mock_req.call_args[0][0] == "POST"
            assert mock_req.call_args[0][1] == "/rest/api/3/issue/TEST-1/transitions"

    async def test_transition_payload_without_comment(self, server_client):
        with patch.object(server_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await server_client.transition_issue("TEST-1", "31")
            payload = mock_req.call_args[1]["json"]
            assert payload == {"transition": {"id": "31"}}
            assert "update" not in payload

    async def test_transition_embeds_comment_in_payload(self, server_client):
        with patch.object(server_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await server_client.transition_issue("TEST-1", "31", comment="done")
            payload = mock_req.call_args[1]["json"]
            assert payload["transition"] == {"id": "31"}
            assert payload["update"]["comment"][0]["add"]["body"] == "done"
            assert mock_req.call_count == 1

    async def test_transition_cloud_comment_adf(self, cloud_client):
        with patch.object(cloud_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await cloud_client.transition_issue("TEST-1", "31", comment="done")
            payload = mock_req.call_args[1]["json"]
            body = payload["update"]["comment"][0]["add"]["body"]
            assert body["type"] == "doc"

    async def test_transition_without_comment_single_call(self, server_client):
        with patch.object(server_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await server_client.transition_issue("TEST-1", "31")
            assert mock_req.call_count == 1

    async def test_transition_returns_id(self, server_client):
        with patch.object(server_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            result = await server_client.transition_issue("TEST-1", "31")
            assert result["transition_id"] == "31"


class TestGetCreateMeta:
    async def test_list_types_endpoint(self, cloud_client):
        with patch.object(cloud_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"projects": [{"issuetypes": [
                {"id": "1", "name": "Bug", "subtask": False}
            ]}]}
            result = await cloud_client.get_create_meta("TEST")
            endpoint = mock_req.call_args[0][1]
            assert endpoint == "/rest/api/3/issue/createmeta"
            assert result["issue_types"][0]["name"] == "Bug"

    async def test_get_fields_calls_two_endpoints(self, cloud_client):
        call_log = []

        async def mock_req(method, endpoint, **kwargs):
            call_log.append(endpoint)
            if "issuetypes/1" in endpoint:
                return {"fields": [
                    {"fieldId": "summary", "name": "Summary", "required": True},
                ]}
            return {"projects": [{"issuetypes": [
                {"id": "1", "name": "Bug", "subtask": False}
            ]}]}

        with patch.object(cloud_client, '_make_request', side_effect=mock_req):
            result = await cloud_client.get_create_meta("TEST", "Bug")
            assert len(call_log) == 2
            assert result["fields"][0]["required"] is True

    async def test_unknown_type_raises(self, cloud_client):
        with patch.object(cloud_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"projects": [{"issuetypes": [
                {"id": "1", "name": "Bug", "subtask": False}
            ]}]}
            with pytest.raises(ValueError, match="not found"):
                await cloud_client.get_create_meta("TEST", "NonExistent")

    async def test_transforms_allowed_values(self, cloud_client):
        call_count = 0

        async def mock_req(method, endpoint, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"projects": [{"issuetypes": [{"id": "1", "name": "Bug", "subtask": False}]}]}
            return {"fields": [
                {"fieldId": "priority", "name": "Priority", "required": False,
                 "allowedValues": [{"name": "High"}, {"name": "Low"}]},
            ]}

        with patch.object(cloud_client, '_make_request', side_effect=mock_req):
            result = await cloud_client.get_create_meta("TEST", "Bug")
            assert result["fields"][0]["allowed"] == ["High", "Low"]

    async def test_required_fields_sorted_first(self, cloud_client):
        call_count = 0

        async def mock_req(method, endpoint, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"projects": [{"issuetypes": [{"id": "1", "name": "Bug", "subtask": False}]}]}
            return {"fields": [
                {"fieldId": "labels", "name": "Labels", "required": False},
                {"fieldId": "summary", "name": "Summary", "required": True},
            ]}

        with patch.object(cloud_client, '_make_request', side_effect=mock_req):
            result = await cloud_client.get_create_meta("TEST", "Bug")
            assert result["fields"][0]["name"] == "Summary"
            assert result["fields"][0]["required"] is True


class TestOtherEndpoints:
    async def test_get_project_endpoint(self, cloud_client):
        with patch.object(cloud_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"key": "TEST"}
            await cloud_client.get_project("TEST")
            endpoint = mock_req.call_args[0][1]
            assert endpoint == "/rest/api/3/project/TEST"

    async def test_get_comments_pages_and_transforms(self, cloud_client):
        with patch.object(cloud_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {
                "comments": [{"author": {"displayName": "Jude"}, "body": "hi",
                              "created": "2025-01-01"}],
                "total": 9,
            }
            result = await cloud_client.get_comments("TEST-1", max_results=2, start_at=4)
            assert mock_req.call_args[0][1] == "/rest/api/3/issue/TEST-1/comment"
            assert mock_req.call_args[1]["params"] == {"maxResults": 2, "startAt": 4}
            assert result["comments"][0]["body"] == "hi"
            assert result["total"] == 9
            assert result["start_at"] == 4
            assert result["max_results"] == 2

    async def test_get_comments_flattens_adf_body(self, cloud_client):
        with patch.object(cloud_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"comments": [{
                "author": {"displayName": "Jude"},
                "body": {"type": "doc", "version": 1, "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "rich"}]}]},
                "created": "2025-01-01",
            }], "total": 1}
            result = await cloud_client.get_comments("TEST-1")
            assert result["comments"][0]["body"] == "rich"

    async def test_get_fields_transforms_definitions(self, server_client):
        with patch.object(server_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = [
                {"id": "summary", "name": "Summary", "custom": False,
                 "schema": {"type": "string"}},
            ]
            result = await server_client.get_fields()
            assert mock_req.call_args[0][1] == "/rest/api/2/field"
            assert result["fields"] == [
                {"id": "summary", "name": "Summary", "custom": False, "type": "string"},
            ]

    async def test_get_myself_cloud_uses_account_id(self, cloud_client):
        with patch.object(cloud_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"accountId": "acc1", "displayName": "Jude",
                                    "emailAddress": "a@x", "active": True}
            result = await cloud_client.get_myself()
            assert mock_req.call_args[0][1] == "/rest/api/3/myself"
            assert result == {"id": "acc1", "display_name": "Jude",
                             "email": "a@x", "active": True}

    async def test_get_myself_server_uses_name(self, server_client):
        with patch.object(server_client, '_make_request', new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"name": "jsmith", "key": "jsmith",
                                    "displayName": "J Smith", "active": True}
            result = await server_client.get_myself()
            assert mock_req.call_args[0][1] == "/rest/api/2/myself"
            assert result["id"] == "jsmith"


def _mock_session(responses):
    """Build a mock aiohttp session that yields responses in order."""
    it = iter(responses)

    @asynccontextmanager
    async def mock_request(*args, **kwargs):
        r = next(it)
        if isinstance(r, Exception):
            raise r
        yield r

    session = MagicMock()
    session.request = mock_request
    session.close = AsyncMock()
    return session


def _resp(status=200, json_data=None, headers=None, text=""):
    r = MagicMock(status=status, reason="OK" if status < 400 else "Error")
    r.headers = headers or {}
    r.json = AsyncMock(return_value=json_data or {})
    r.text = AsyncMock(return_value=text)
    return r


class TestMakeRequest:
    """Tests for _make_request retry, backoff, and error handling at HTTP level."""

    async def test_successful_request(self):
        session = _mock_session([_resp(200, {"key": "val"})])
        client = AsyncJiraClient("https://j.test", "tok", session=session)
        result = await client._make_request("GET", "/test")
        assert result == {"key": "val"}

    async def test_204_returns_empty_dict(self):
        session = _mock_session([_resp(204)])
        client = AsyncJiraClient("https://j.test", "tok", session=session)
        result = await client._make_request("PUT", "/test")
        assert result == {}

    async def test_retries_on_429(self):
        session = _mock_session([_resp(429), _resp(200, {"ok": True})])
        client = AsyncJiraClient("https://j.test", "tok", session=session)
        with patch('jira_client.asyncio.sleep', new_callable=AsyncMock):
            result = await client._make_request("GET", "/test")
        assert result == {"ok": True}

    async def test_retry_after_header_respected(self):
        session = _mock_session([_resp(429, headers={"Retry-After": "5"}), _resp(200)])
        client = AsyncJiraClient("https://j.test", "tok", session=session)
        with patch('jira_client.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await client._make_request("GET", "/test")
            mock_sleep.assert_called_with(5.0)

    async def test_429_exhausts_retries(self):
        session = _mock_session([_resp(429)] * 4)
        client = AsyncJiraClient("https://j.test", "tok", session=session)
        with patch('jira_client.asyncio.sleep', new_callable=AsyncMock):
            with pytest.raises(Exception, match="Rate limited"):
                await client._make_request("GET", "/test")

    async def test_http_error_raises(self):
        session = _mock_session([_resp(404, text='{"error":"not found"}')])
        client = AsyncJiraClient("https://j.test", "tok", session=session)
        with pytest.raises(Exception, match="404"):
            await client._make_request("GET", "/test")

    async def test_http_error_carries_status_and_body(self):
        body = '{"errorMessages":["Issue does not exist"]}'
        session = _mock_session([_resp(404, text=body)])
        client = AsyncJiraClient("https://j.test", "tok", session=session)
        with pytest.raises(JiraHttpError) as exc_info:
            await client._make_request("GET", "/test")
        assert exc_info.value.status == 404
        assert exc_info.value.body == body
        assert str(exc_info.value).startswith("JIRA API request failed: 404")

    async def test_connection_error_retries(self):
        session = _mock_session([aiohttp.ClientError("reset"), _resp(200, {"ok": True})])
        client = AsyncJiraClient("https://j.test", "tok", session=session)
        with patch('jira_client.asyncio.sleep', new_callable=AsyncMock):
            result = await client._make_request("GET", "/test")
        assert result == {"ok": True}

    async def test_connection_error_exhausts_retries(self):
        session = _mock_session([aiohttp.ClientError("refused")] * 4)
        client = AsyncJiraClient("https://j.test", "tok", session=session)
        with patch('jira_client.asyncio.sleep', new_callable=AsyncMock):
            with pytest.raises(Exception, match="failed after"):
                await client._make_request("GET", "/test")

    async def test_exponential_backoff_delay(self):
        session = _mock_session([_resp(429), _resp(429), _resp(200)])
        client = AsyncJiraClient("https://j.test", "tok", session=session)
        with patch('jira_client.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await client._make_request("GET", "/test")
            # Filter out sub-second throttler sleeps
            retry_delays = [c.args[0] for c in mock_sleep.call_args_list if c.args[0] >= 0.5]
            assert retry_delays == [1.0, 2.0]

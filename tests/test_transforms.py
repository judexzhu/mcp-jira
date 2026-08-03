"""Tests for transform functions and ADF conversion."""

from jira_client import (
    _adf_to_text,
    _text_to_adf,
    _transform_issue,
    _transform_comment,
    _transform_link,
    _transform_transition,
)


class TestAdfToText:
    def test_string_passthrough(self):
        assert _adf_to_text("hello") == "hello"

    def test_text_node(self):
        assert _adf_to_text({"type": "text", "text": "hello"}) == "hello"

    def test_hard_break(self):
        assert _adf_to_text({"type": "hardBreak"}) == "\n"

    def test_mention(self):
        node = {"type": "mention", "attrs": {"text": "@jude"}}
        assert _adf_to_text(node) == "@jude"

    def test_emoji(self):
        node = {"type": "emoji", "attrs": {"shortName": ":thumbsup:"}}
        assert _adf_to_text(node) == ":thumbsup:"

    def test_inline_card(self):
        node = {"type": "inlineCard", "attrs": {"url": "https://example.com"}}
        assert _adf_to_text(node) == "https://example.com"

    def test_paragraph(self):
        node = {
            "type": "paragraph",
            "content": [{"type": "text", "text": "hello world"}]
        }
        assert _adf_to_text(node) == "hello world\n"

    def test_nested_paragraphs(self):
        doc = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "line 1"}]},
                {"type": "paragraph", "content": [{"type": "text", "text": "line 2"}]},
            ]
        }
        assert _adf_to_text(doc) == "line 1\nline 2\n"

    def test_heading(self):
        node = {
            "type": "heading",
            "content": [{"type": "text", "text": "Title"}]
        }
        assert _adf_to_text(node) == "Title\n"

    def test_list(self):
        assert _adf_to_text([
            {"type": "text", "text": "a"},
            {"type": "text", "text": "b"},
        ]) == "ab"

    def test_none_returns_empty(self):
        assert _adf_to_text(None) == ""

    def test_int_returns_empty(self):
        assert _adf_to_text(42) == ""

    def test_empty_dict(self):
        assert _adf_to_text({}) == ""

    def test_code_block(self):
        node = {
            "type": "codeBlock",
            "content": [{"type": "text", "text": "print('hi')"}]
        }
        assert _adf_to_text(node) == "print('hi')\n"


class TestTextToAdf:
    def test_basic_structure(self):
        result = _text_to_adf("hello")
        assert result["type"] == "doc"
        assert result["version"] == 1
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "paragraph"
        assert result["content"][0]["content"][0]["text"] == "hello"

    def test_round_trip(self):
        text = "This is a test message"
        adf = _text_to_adf(text)
        assert _adf_to_text(adf).strip() == text


class TestTransformIssue:
    def test_extracts_key_and_summary(self):
        issue = {"key": "TEST-1", "fields": {"summary": "Bug report"}}
        result = _transform_issue(issue)
        assert result["key"] == "TEST-1"
        assert result["summary"] == "Bug report"

    def test_extracts_nested_status(self):
        issue = {"key": "TEST-1", "fields": {
            "summary": "x",
            "status": {"name": "In Progress", "id": "3"}
        }}
        result = _transform_issue(issue)
        assert result["status"] == "In Progress"

    def test_extracts_nested_assignee(self):
        issue = {"key": "TEST-1", "fields": {
            "summary": "x",
            "assignee": {"displayName": "Jude", "emailAddress": "j@r.com"}
        }}
        result = _transform_issue(issue)
        assert result["assignee"] == "Jude"

    def test_extracts_nested_priority(self):
        issue = {"key": "TEST-1", "fields": {
            "summary": "x",
            "priority": {"name": "High", "id": "2"}
        }}
        result = _transform_issue(issue)
        assert result["priority"] == "High"

    def test_extracts_issue_type(self):
        issue = {"key": "TEST-1", "fields": {
            "summary": "x",
            "issuetype": {"name": "Bug", "id": "1"}
        }}
        result = _transform_issue(issue)
        assert result["type"] == "Bug"

    def test_includes_timestamps(self):
        issue = {"key": "TEST-1", "fields": {
            "summary": "x",
            "created": "2025-01-01T00:00:00",
            "updated": "2025-01-02T00:00:00",
        }}
        result = _transform_issue(issue)
        assert result["created"] == "2025-01-01T00:00:00"
        assert result["updated"] == "2025-01-02T00:00:00"

    def test_converts_adf_description(self):
        issue = {"key": "TEST-1", "fields": {
            "summary": "x",
            "description": {
                "type": "doc",
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": "desc"}]}]
            }
        }}
        result = _transform_issue(issue)
        assert result["desc"] == "desc"

    def test_string_description_passthrough(self):
        issue = {"key": "TEST-1", "fields": {"summary": "x", "description": "plain"}}
        result = _transform_issue(issue)
        assert result["desc"] == "plain"

    def test_omits_empty_labels(self):
        issue = {"key": "TEST-1", "fields": {"summary": "x", "labels": []}}
        result = _transform_issue(issue)
        assert "labels" not in result

    def test_includes_nonempty_labels(self):
        issue = {"key": "TEST-1", "fields": {"summary": "x", "labels": ["bug", "urgent"]}}
        result = _transform_issue(issue)
        assert result["labels"] == ["bug", "urgent"]

    def test_missing_optional_fields(self):
        issue = {"key": "TEST-1", "fields": {"summary": "x"}}
        result = _transform_issue(issue)
        assert "status" not in result
        assert "assignee" not in result
        assert "priority" not in result
        assert "desc" not in result


class TestTransformComment:
    def test_extracts_fields(self):
        comment = {
            "author": {"displayName": "Jude"},
            "body": "a comment",
            "created": "2025-01-01T00:00:00",
        }
        result = _transform_comment(comment)
        assert result["author"] == "Jude"
        assert result["body"] == "a comment"
        assert result["created"] == "2025-01-01T00:00:00"

    def test_omits_updated_when_same_as_created(self):
        comment = {
            "author": {"displayName": "Jude"},
            "body": "text",
            "created": "2025-01-01T00:00:00",
            "updated": "2025-01-01T00:00:00",
        }
        result = _transform_comment(comment)
        assert "updated" not in result

    def test_includes_updated_when_different(self):
        comment = {
            "author": {"displayName": "Jude"},
            "body": "text",
            "created": "2025-01-01T00:00:00",
            "updated": "2025-01-02T00:00:00",
        }
        result = _transform_comment(comment)
        assert result["updated"] == "2025-01-02T00:00:00"

    def test_converts_adf_body(self):
        comment = {
            "author": {"displayName": "Jude"},
            "body": {
                "type": "doc",
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": "adf body"}]}]
            },
            "created": "2025-01-01T00:00:00",
        }
        result = _transform_comment(comment)
        assert result["body"] == "adf body"


class TestTransformLink:
    def test_extracts_fields(self):
        linked = {
            "key": "TEST-2",
            "fields": {
                "summary": "linked issue",
                "status": {"name": "Done"}
            }
        }
        result = _transform_link(linked)
        assert result == {"key": "TEST-2", "summary": "linked issue", "status": "Done"}


class TestTransformTransition:
    def test_extracts_fields(self):
        transition = {
            "id": "31",
            "name": "Done",
            "to": {"name": "Done", "id": "10001"}
        }
        result = _transform_transition(transition)
        assert result == {"id": "31", "name": "Done", "to": "Done"}

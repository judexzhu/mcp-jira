"""
JIRA client module for the MCP server.
Handles interactions with the JIRA API.
"""
import os
from typing import Dict, List, Optional, Any
from jira import JIRA


class JiraClient:
    """
    Client for interacting with JIRA API.
    Handles authentication and provides methods for working with JIRA issues.
    """

    def __init__(self, server_url: str, email: str, api_token: str):
        """
        Initialize a JIRA client with the provided credentials.

        Args:
            server_url: URL of the JIRA server
            email: Email associated with the API token (not used with Bearer auth)
            api_token: JIRA API token for authentication
        """
        self.server_url = server_url
        
        # Use Bearer token authentication instead of Basic Auth
        options = {
            'server': server_url,
            'headers': {
                'Authorization': f'Bearer {api_token}'
            }
        }
        self.jira = JIRA(options=options)

    def search_issues(self, jql: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Search for issues using JQL (JIRA Query Language).

        Args:
            jql: JQL query string
            max_results: Maximum number of results to return

        Returns:
            List of issues matching the query
        """
        issues = self.jira.search_issues(jql_str=jql, maxResults=max_results)
        return [self._format_issue_summary(issue) for issue in issues]

    def get_issue(self, issue_key: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific issue.

        Args:
            issue_key: The issue key (e.g., PROJECT-123)

        Returns:
            Detailed issue information
        """
        issue = self.jira.issue(issue_key, expand='renderedFields,changelog,operations,editmeta')
        return self._format_issue_detail(issue)

    def get_issue_comments(self, issue_key: str) -> List[Dict[str, Any]]:
        """
        Get all comments for a specific issue.

        Args:
            issue_key: The issue key (e.g., PROJECT-123)

        Returns:
            List of comments for the issue
        """
        comments = self.jira.comments(issue_key)
        return [
            {
                "id": comment.id,
                "body": comment.body,
                "author": getattr(comment, "author", {}).get("displayName", "Unknown"),
                "created": comment.created,
                "updated": comment.updated
            }
            for comment in comments
        ]

    def get_issue_links(self, issue_key: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all links for a specific issue, categorized by link type.

        Args:
            issue_key: The issue key (e.g., PROJECT-123)

        Returns:
            Dictionary of link types to lists of linked issues
        """
        issue = self.jira.issue(issue_key)
        links = {}
        
        if hasattr(issue.fields, 'issuelinks') and issue.fields.issuelinks:
            for link in issue.fields.issuelinks:
                link_type = link.type.name
                
                if not link_type in links:
                    links[link_type] = []
                
                if hasattr(link, 'inwardIssue'):
                    linked_issue = link.inwardIssue
                    direction = 'inward'
                elif hasattr(link, 'outwardIssue'):
                    linked_issue = link.outwardIssue
                    direction = 'outward'
                else:
                    continue
                
                links[link_type].append({
                    "key": linked_issue.key,
                    "summary": linked_issue.fields.summary,
                    "status": linked_issue.fields.status.name,
                    "direction": direction
                })
        
        return links

    def get_epic_issues(self, epic_key: str) -> List[Dict[str, Any]]:
        """
        Get all issues that belong to a specific epic.

        Args:
            epic_key: The epic issue key (e.g., PROJECT-123)

        Returns:
            List of issues in the epic
        """
        # JQL to find all issues in an epic
        jql = f'parent = {epic_key} OR "Epic Link" = {epic_key}'
        issues = self.jira.search_issues(jql_str=jql, maxResults=100)
        return [self._format_issue_summary(issue) for issue in issues]

    def get_subtasks(self, issue_key: str) -> List[Dict[str, Any]]:
        """
        Get all subtasks for a specific issue.

        Args:
            issue_key: The parent issue key (e.g., PROJECT-123)

        Returns:
            List of subtasks for the issue
        """
        issue = self.jira.issue(issue_key)
        subtasks = []
        
        if hasattr(issue.fields, 'subtasks') and issue.fields.subtasks:
            for subtask in issue.fields.subtasks:
                subtasks.append({
                    "key": subtask.key,
                    "summary": subtask.fields.summary,
                    "status": subtask.fields.status.name,
                    "type": subtask.fields.issuetype.name
                })
        
        return subtasks

    def _format_issue_summary(self, issue) -> Dict[str, Any]:
        """
        Format basic issue information for summary display.

        Args:
            issue: JIRA issue object

        Returns:
            Dictionary with summarized issue information
        """
        return {
            "key": issue.key,
            "summary": issue.fields.summary,
            "status": issue.fields.status.name,
            "issuetype": issue.fields.issuetype.name,
            "created": issue.fields.created,
            "updated": issue.fields.updated,
            "assignee": getattr(issue.fields.assignee, 'displayName', 'Unassigned') if issue.fields.assignee else 'Unassigned',
            "priority": getattr(issue.fields.priority, 'name', 'None') if hasattr(issue.fields, 'priority') and issue.fields.priority else 'None'
        }

    def _format_issue_detail(self, issue) -> Dict[str, Any]:
        """
        Format detailed issue information.

        Args:
            issue: JIRA issue object

        Returns:
            Dictionary with detailed issue information
        """
        detail = self._format_issue_summary(issue)
        
        # Add additional fields for detailed view
        detail.update({
            "description": issue.fields.description or '',
            "reporter": getattr(issue.fields.reporter, 'displayName', 'Unknown') if issue.fields.reporter else 'Unknown',
            "components": [c.name for c in issue.fields.components] if hasattr(issue.fields, 'components') else [],
            "labels": issue.fields.labels if hasattr(issue.fields, 'labels') else [],
            "fixVersions": [v.name for v in issue.fields.fixVersions] if hasattr(issue.fields, 'fixVersions') else [],
            "affectedVersions": [v.name for v in issue.fields.versions] if hasattr(issue.fields, 'versions') else [],
            "resolution": getattr(issue.fields.resolution, 'name', None) if hasattr(issue.fields, 'resolution') and issue.fields.resolution else None,
            "resolutionDate": issue.fields.resolutiondate if hasattr(issue.fields, 'resolutiondate') else None,
            "duedate": issue.fields.duedate if hasattr(issue.fields, 'duedate') else None,
            "watches": issue.fields.watches.watchCount if hasattr(issue.fields, 'watches') else 0
        })
        
        # Add epic link if it exists
        if hasattr(issue.fields, 'customfield_10014') and issue.fields.customfield_10014:  # Epic Link field (may vary by JIRA instance)
            detail["epicLink"] = issue.fields.customfield_10014
        
        # Add parent if it exists
        if hasattr(issue.fields, 'parent') and issue.fields.parent:
            detail["parent"] = {
                "key": issue.fields.parent.key,
                "summary": issue.fields.parent.fields.summary
            }
            
        return detail

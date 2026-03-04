#!/usr/bin/env python3
"""
Simple test script for the async JIRA MCP server.
This script verifies that the async implementation works correctly.
"""
import asyncio
import os
from dotenv import load_dotenv
from jira_client import AsyncJiraClient

# Load environment variables
load_dotenv()

async def test_basic_operations():
    """Test basic async operations."""
    
    JIRA_SERVER_URL = os.getenv("JIRA_SERVER_URL")
    JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
    
    if not JIRA_SERVER_URL or not JIRA_API_TOKEN:
        print("❌ Please set JIRA_SERVER_URL and JIRA_API_TOKEN in your .env file")
        return False
    
    print("🧪 Testing Async JIRA Client")
    print("=" * 30)
    
    # Use conservative rate limiting for testing
    max_concurrent = int(os.getenv("MAX_CONCURRENT_REQUESTS", 2))
    client = AsyncJiraClient(JIRA_SERVER_URL, JIRA_API_TOKEN, max_concurrent_requests=max_concurrent)
    
    try:
        # Test 1: Search for issues
        print("🔍 Test 1: Searching for issues...")
        issues = await client.search_issues("ORDER BY created DESC", 3)
        print(f"✅ Found {len(issues)} issues")
        
        if not issues:
            print("⚠️  No issues found - this may indicate limited JIRA access")
            await client.close()
            return
        
        # Test 2: Get issue details
        print(f"\n📋 Test 2: Getting details for issue {issues[0]['key']}...")
        issue_detail = await client.get_issue(issues[0]['key'])
        summary = issue_detail.get('summary', 'No summary')
        print(f"✅ Retrieved issue: {summary[:50]}...")
        
        # Test 3: Get issue comments
        print(f"\n💬 Test 3: Getting comments for issue {issues[0]['key']}...")
        comments = await client.get_issue_comments(issues[0]['key'])
        print(f"✅ Found {len(comments)} comments")
        
        # Test 4: Get issue links
        print(f"\n🔗 Test 4: Getting links for issue {issues[0]['key']}...")
        links = await client.get_issue_links(issues[0]['key'])
        print(f"✅ Found {len(links)} link types")
        
        # Test 5: Concurrent operations
        print(f"\n⚡ Test 5: Concurrent operations...")
        tasks = [
            client.get_issue(issues[0]['key']),
            client.get_issue_comments(issues[0]['key'])
        ]
        results = await asyncio.gather(*tasks)
        print(f"✅ Completed {len(results)} concurrent operations")
        
        print(f"\n🎉 All tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        if "429" in str(e):
            print("💡 Rate limiting detected. Try:")
            print("   • Reducing MAX_CONCURRENT_REQUESTS in your .env file")
            print("   • Running 'python check_rate_limits.py' to check your limits")
            print("   • Waiting a few minutes before retrying")
        return False
    
    finally:
        await client.close()

async def test_error_handling():
    """Test error handling."""
    print(f"\n🛡️  Testing Error Handling")
    print("=" * 30)
    
    JIRA_SERVER_URL = os.getenv("JIRA_SERVER_URL")
    JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
    
    if not JIRA_SERVER_URL or not JIRA_API_TOKEN:
        print("❌ Skipping error handling tests (no credentials)")
        return True
    
    # Use very conservative settings for error testing
    client = AsyncJiraClient(JIRA_SERVER_URL, JIRA_API_TOKEN, max_concurrent_requests=1)
    
    try:
        # Test invalid issue key
        print("🔍 Testing invalid issue key...")
        try:
            await client.get_issue("INVALID-999999")
            print("❌ Should have failed for invalid issue")
            return False
        except Exception as e:
            if "404" in str(e) or "400" in str(e):
                print("✅ Correctly handled invalid issue key")
            else:
                print(f"⚠️  Unexpected error (but handled): {e}")
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(1)
        
        # Test invalid JQL
        print("🔍 Testing invalid JQL...")
        try:
            await client.search_issues("INVALID JQL SYNTAX HERE")
            print("❌ Should have failed for invalid JQL")
            return False
        except Exception as e:
            if "400" in str(e):
                print("✅ Correctly handled invalid JQL")
            else:
                print(f"⚠️  Unexpected error (but handled): {e}")
        
        print("✅ Error handling tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Error handling test failed: {str(e)}")
        return False
    
    finally:
        await client.close()

async def main():
    """Run all tests."""
    print("🚀 Async JIRA Client Test Suite")
    print("=" * 40)
    
    # Check credentials
    if not os.getenv("JIRA_SERVER_URL") or not os.getenv("JIRA_API_TOKEN"):
        print("""
❌ Missing JIRA credentials!

Please create a .env file with:
JIRA_SERVER_URL=https://your-company.atlassian.net
JIRA_API_TOKEN=your_api_token_here

Get your API token from: https://id.atlassian.com/manage-profile/security/api-tokens
""")
        return
    
    # Show current configuration
    max_concurrent = int(os.getenv("MAX_CONCURRENT_REQUESTS", 2))
    print(f"📊 Configuration:")
    print(f"   MAX_CONCURRENT_REQUESTS: {max_concurrent}")
    print(f"   JIRA_SERVER_URL: {os.getenv('JIRA_SERVER_URL')}")
    print()
    
    try:
        # Run tests
        basic_test_passed = await test_basic_operations()
        error_test_passed = await test_error_handling()
        
        print(f"\n📊 Test Results")
        print("=" * 20)
        print(f"Basic Operations: {'✅ PASS' if basic_test_passed else '❌ FAIL'}")
        print(f"Error Handling:   {'✅ PASS' if error_test_passed else '❌ FAIL'}")
        
        if basic_test_passed and error_test_passed:
            print(f"\n🎉 All tests passed! The async JIRA client is working correctly.")
            print(f"💡 You can now run the MCP server with: python jira_mcp_server.py")
            print(f"💡 To check your rate limits, run: python check_rate_limits.py")
        else:
            print(f"\n❌ Some tests failed. Please check your JIRA configuration.")
            print(f"💡 If you see 429 errors, try reducing MAX_CONCURRENT_REQUESTS")
            
    except KeyboardInterrupt:
        print(f"\n⏹️  Tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error during testing: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 
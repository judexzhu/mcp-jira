#!/usr/bin/env python3
"""
Test script for the JIRA MCP Server.
This script tests the server functionality and basic MCP compatibility.
"""
import asyncio
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def test_server_components():
    """Test the server components directly."""
    print("🧪 Testing JIRA MCP Server Components")
    print("=" * 50)
    
    # Check if credentials are configured
    if not os.getenv("JIRA_SERVER_URL") or not os.getenv("JIRA_API_TOKEN"):
        print("""
❌ Missing JIRA credentials!

Please create a .env file with:
JIRA_SERVER_URL=https://your-company.atlassian.net
JIRA_API_TOKEN=your_api_token_here
""")
        return False
    
    try:
        # Import server components
        from jira_mcp_server import (
            get_jira_client, 
            jira_search_issues, 
            jira_get_issue_details,
            jira_get_issue_comments,
            jira_get_issue_links
        )
        
        print("✅ Successfully imported server components")
        
        # Test 1: JIRA client initialization
        print("\n📋 Test 1: JIRA client initialization...")
        client = await get_jira_client()
        print("✅ JIRA client initialized successfully")
        
        # Test 2: Search functionality
        print("\n📋 Test 2: Testing jira_search_issues...")
        issues = await jira_search_issues("ORDER BY created DESC", 3)
        print(f"✅ Found {len(issues)} issues")
        
        if not issues:
            print("⚠️  No issues found - this may indicate limited JIRA access")
            await client.close()
            return True
        
        # Test 3: Get issue details
        print(f"\n📋 Test 3: Testing jira_get_issue_details for {issues[0]['key']}...")
        issue_detail = await jira_get_issue_details(issues[0]['key'])
        summary = issue_detail.get('fields', {}).get('summary', 'No summary')
        print(f"✅ Retrieved issue: {summary[:50]}...")
        
        # Test 4: Get issue comments
        print(f"\n📋 Test 4: Testing jira_get_issue_comments for {issues[0]['key']}...")
        comments = await jira_get_issue_comments(issues[0]['key'])
        print(f"✅ Found {len(comments)} comments")
        
        # Test 5: Get issue links
        print(f"\n📋 Test 5: Testing jira_get_issue_links for {issues[0]['key']}...")
        links = await jira_get_issue_links(issues[0]['key'])
        total_links = sum(len(link_list) for link_list in links.values())
        print(f"✅ Found {total_links} links across {len(links)} link types")
        
        # Clean up
        await client.close()
        
        print("\n🎉 All server component tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        print(f"   Error type: {type(e).__name__}")
        return False

async def test_mcp_server_startup():
    """Test that the MCP server can start up correctly."""
    print("\n🚀 Testing MCP Server Startup")
    print("=" * 35)
    
    try:
        import subprocess
        import signal
        import time
        
        # Start the server process
        print("📋 Starting MCP server process...")
        process = subprocess.Popen(
            [sys.executable, "jira_mcp_server.py"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Give it a moment to start
        time.sleep(2)
        
        # Check if it's still running
        if process.poll() is None:
            print("✅ MCP server started successfully")
            
            # Terminate the process
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            
            print("✅ MCP server shutdown cleanly")
            return True
        else:
            # Process exited, check for errors
            stdout, stderr = process.communicate()
            print(f"❌ MCP server failed to start")
            if stderr:
                print(f"   Error: {stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Server startup test failed: {e}")
        return False

async def test_mcp_imports():
    """Test that all MCP-related imports work correctly."""
    print("\n📦 Testing MCP Dependencies")
    print("=" * 30)
    
    try:
        # Test FastMCP import
        from mcp.server.fastmcp import FastMCP
        print("✅ FastMCP imported successfully")
        
        # Test MCP types
        from mcp.types import Resource, Tool, TextContent
        print("✅ MCP types imported successfully")
        
        # Test that we can create a FastMCP instance
        test_mcp = FastMCP("Test Server")
        print("✅ FastMCP instance created successfully")
        
        return True
        
    except ImportError as e:
        print(f"❌ MCP import failed: {e}")
        print("💡 This suggests MCP dependencies are not properly installed")
        return False
    except Exception as e:
        print(f"❌ MCP test failed: {e}")
        return False

async def main():
    """Run all tests."""
    print("🚀 JIRA MCP Server Test Suite")
    print("=" * 40)
    
    # Check if server file exists
    if not os.path.exists("jira_mcp_server.py"):
        print("❌ jira_mcp_server.py not found in current directory")
        return
    
    # Check credentials
    credentials_available = bool(os.getenv("JIRA_SERVER_URL") and os.getenv("JIRA_API_TOKEN"))
    if not credentials_available:
        print("⚠️  JIRA credentials not configured")
        print("   Set JIRA_SERVER_URL and JIRA_API_TOKEN in .env file for full testing")
        print("   Some tests will be skipped")
    
    try:
        # Test 1: MCP dependencies
        mcp_imports_passed = await test_mcp_imports()
        
        # Test 2: Server components (only if credentials available)
        components_passed = True
        if credentials_available:
            components_passed = await test_server_components()
        else:
            print("\n⏭️  Skipping server component tests (no JIRA credentials)")
        
        # Test 3: Server startup
        startup_passed = await test_mcp_server_startup()
        
        # Summary
        print(f"\n📊 Test Results")
        print("=" * 20)
        print(f"MCP Dependencies: {'✅ PASS' if mcp_imports_passed else '❌ FAIL'}")
        print(f"Server Components:{'✅ PASS' if components_passed else '❌ FAIL'}")
        print(f"Server Startup:   {'✅ PASS' if startup_passed else '❌ FAIL'}")
        
        all_passed = mcp_imports_passed and components_passed and startup_passed
        
        if all_passed:
            print(f"\n🎉 All tests passed!")
            print(f"💡 The server is ready for use with MCP clients")
            print(f"\n📋 Next steps:")
            print(f"   • Add the server to your Claude Desktop configuration")
        else:
            print(f"\n❌ Some tests failed. Check the error messages above.")
            if not mcp_imports_passed:
                print(f"💡 MCP dependency issues - try: uv add 'mcp[cli]'")
            if not startup_passed:
                print(f"💡 Server startup issues - check environment configuration")
            
    except KeyboardInterrupt:
        print(f"\n⏹️  Tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error during testing: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 
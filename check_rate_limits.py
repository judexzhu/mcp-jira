#!/usr/bin/env python3
"""
Check JIRA API rate limits by examining response headers.
This script will show you the current rate limiting information for your JIRA instance.
"""
import asyncio
import os
from dotenv import load_dotenv
import aiohttp
import json

# Load environment variables
load_dotenv()

async def check_rate_limits():
    """Check the current rate limits for your JIRA API token."""
    
    JIRA_SERVER_URL = os.getenv("JIRA_SERVER_URL")
    JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
    
    if not JIRA_SERVER_URL or not JIRA_API_TOKEN:
        print("❌ Please set JIRA_SERVER_URL and JIRA_API_TOKEN in your .env file")
        return
    
    print("🔍 Checking JIRA API Rate Limits")
    print("=" * 40)
    print(f"JIRA Server: {JIRA_SERVER_URL}")
    print()
    
    # Prepare headers
    headers = {
        "Authorization": f"Bearer {JIRA_API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            # Make a simple API call to get rate limit headers
            url = f"{JIRA_SERVER_URL}/rest/api/2/myself"
            
            print("📡 Making test API call to check rate limits...")
            async with session.get(url, headers=headers) as response:
                print(f"✅ Response Status: {response.status}")
                print()
                
                # Check for rate limiting headers
                rate_limit_headers = {}
                for header_name, header_value in response.headers.items():
                    if any(keyword in header_name.lower() for keyword in 
                          ['rate', 'limit', 'remaining', 'reset', 'retry', 'quota']):
                        rate_limit_headers[header_name] = header_value
                
                if rate_limit_headers:
                    print("📊 Rate Limiting Headers Found:")
                    print("-" * 30)
                    for header, value in rate_limit_headers.items():
                        print(f"  {header}: {value}")
                else:
                    print("ℹ️  No explicit rate limiting headers found in response")
                
                print()
                
                # Show all headers for debugging
                print("📋 All Response Headers:")
                print("-" * 30)
                for header, value in response.headers.items():
                    print(f"  {header}: {value}")
                
                print()
                
                # Get user info to verify token works
                if response.status == 200:
                    user_data = await response.json()
                    print("👤 User Information:")
                    print("-" * 20)
                    print(f"  Display Name: {user_data.get('displayName', 'N/A')}")
                    print(f"  Email: {user_data.get('emailAddress', 'N/A')}")
                    print(f"  Account ID: {user_data.get('accountId', 'N/A')}")
                
        except aiohttp.ClientError as e:
            print(f"❌ Error making API call: {e}")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")

async def test_rate_limiting():
    """Test rate limiting by making multiple rapid requests."""
    
    JIRA_SERVER_URL = os.getenv("JIRA_SERVER_URL")
    JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
    
    if not JIRA_SERVER_URL or not JIRA_API_TOKEN:
        return
    
    print("\n⚡ Testing Rate Limiting with Multiple Requests")
    print("=" * 50)
    
    headers = {
        "Authorization": f"Bearer {JIRA_API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    async with aiohttp.ClientSession() as session:
        url = f"{JIRA_SERVER_URL}/rest/api/2/myself"
        
        print("🔄 Making 10 rapid requests to test rate limiting...")
        
        for i in range(10):
            try:
                async with session.get(url, headers=headers) as response:
                    status = response.status
                    
                    # Look for rate limiting info
                    remaining = response.headers.get('X-RateLimit-Remaining', 'N/A')
                    limit = response.headers.get('X-RateLimit-Limit', 'N/A')
                    reset = response.headers.get('X-RateLimit-Reset', 'N/A')
                    retry_after = response.headers.get('Retry-After', 'N/A')
                    
                    print(f"  Request {i+1}: Status {status} | Remaining: {remaining} | Limit: {limit} | Reset: {reset}")
                    
                    if status == 429:
                        print(f"    ⚠️  Rate limited! Retry-After: {retry_after}")
                        break
                        
            except Exception as e:
                print(f"  Request {i+1}: Error - {e}")
            
            # Small delay between requests
            await asyncio.sleep(0.1)

def print_rate_limit_info():
    """Print general information about JIRA rate limits."""
    print("""
📚 JIRA API Rate Limiting Information
====================================

Common Rate Limit Types:

1. **Atlassian Cloud (Standard)**:
   • 300 requests per minute per IP
   • 10 requests per second per user
   • Burst allowance for short periods

2. **Atlassian Cloud (Premium)**:
   • Higher limits based on plan
   • May have different per-user limits

3. **JIRA Server/Data Center**:
   • Configured by administrators
   • Varies by instance

Common Headers to Look For:
• X-RateLimit-Limit: Total requests allowed
• X-RateLimit-Remaining: Requests remaining
• X-RateLimit-Reset: When limit resets
• Retry-After: Seconds to wait before retry

Recommendations:
• Start with 1-2 requests per second
• Monitor response headers
• Implement exponential backoff
• Use batch operations when possible
""")

async def main():
    """Run rate limit checking."""
    print_rate_limit_info()
    
    if not os.getenv("JIRA_SERVER_URL") or not os.getenv("JIRA_API_TOKEN"):
        print("""
❌ Missing JIRA credentials!

Please create a .env file with:
JIRA_SERVER_URL=https://your-company.atlassian.net
JIRA_API_TOKEN=your_api_token_here
""")
        return
    
    try:
        await check_rate_limits()
        await test_rate_limiting()
        
        print(f"\n💡 Recommendations:")
        print(f"   • If you see 429 errors, reduce MAX_CONCURRENT_REQUESTS")
        print(f"   • Start with MAX_CONCURRENT_REQUESTS=2 for testing")
        print(f"   • Monitor the rate limit headers to find optimal settings")
        print(f"   • Consider adding delays between requests if needed")
        
    except KeyboardInterrupt:
        print(f"\n⏹️  Rate limit check interrupted")
    except Exception as e:
        print(f"\n❌ Error during rate limit check: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 
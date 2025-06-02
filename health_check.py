#!/usr/bin/env python3
"""
Health check and monitoring script for JIRA MCP Server.
This script provides comprehensive health monitoring and diagnostics.
"""
import asyncio
import time
import os
import json
import sys
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
from jira_client import AsyncJiraClient

# Load environment variables
load_dotenv()

class HealthChecker:
    """Comprehensive health checker for JIRA MCP Server."""
    
    def __init__(self):
        self.server_url = os.getenv("JIRA_SERVER_URL")
        self.api_token = os.getenv("JIRA_API_TOKEN")
        self.max_concurrent = int(os.getenv("MAX_CONCURRENT_REQUESTS", 5))
        self.client: Optional[AsyncJiraClient] = None
        
    async def initialize(self):
        """Initialize the JIRA client."""
        if not self.server_url or not self.api_token:
            raise ValueError("JIRA_SERVER_URL and JIRA_API_TOKEN must be set")
        
        self.client = AsyncJiraClient(
            self.server_url, 
            self.api_token, 
            max_concurrent_requests=self.max_concurrent
        )
    
    async def cleanup(self):
        """Clean up resources."""
        if self.client:
            await self.client.close()
    
    async def check_connectivity(self) -> Dict[str, Any]:
        """Test basic JIRA connectivity."""
        result = {
            "test": "connectivity",
            "status": "unknown",
            "response_time_ms": 0,
            "details": {}
        }
        
        try:
            start_time = time.time()
            
            # Make a simple API call
            response = await self.client._make_request('GET', '/rest/api/2/myself')
            
            end_time = time.time()
            response_time = (end_time - start_time) * 1000
            
            result.update({
                "status": "healthy",
                "response_time_ms": round(response_time, 2),
                "details": {
                    "user": response.get('displayName', 'Unknown'),
                    "account_id": response.get('accountId', 'Unknown'),
                    "email": response.get('emailAddress', 'Unknown')
                }
            })
            
        except Exception as e:
            result.update({
                "status": "unhealthy",
                "error": str(e)
            })
        
        return result
    
    async def check_search_performance(self) -> Dict[str, Any]:
        """Test search functionality and performance."""
        result = {
            "test": "search_performance",
            "status": "unknown",
            "response_time_ms": 0,
            "details": {}
        }
        
        try:
            start_time = time.time()
            
            # Simple search query
            issues = await self.client.search_issues("ORDER BY created DESC", max_results=5)
            
            end_time = time.time()
            response_time = (end_time - start_time) * 1000
            
            result.update({
                "status": "healthy",
                "response_time_ms": round(response_time, 2),
                "details": {
                    "issues_found": len(issues),
                    "sample_issue": issues[0]['key'] if issues else None
                }
            })
            
        except Exception as e:
            result.update({
                "status": "unhealthy",
                "error": str(e)
            })
        
        return result
    
    async def check_concurrent_performance(self) -> Dict[str, Any]:
        """Test concurrent request handling."""
        result = {
            "test": "concurrent_performance",
            "status": "unknown",
            "response_time_ms": 0,
            "details": {}
        }
        
        try:
            # First get some issue keys
            issues = await self.client.search_issues("ORDER BY created DESC", max_results=3)
            if len(issues) < 2:
                result.update({
                    "status": "skipped",
                    "error": "Need at least 2 issues for concurrent test"
                })
                return result
            
            issue_keys = [issue['key'] for issue in issues[:2]]
            
            start_time = time.time()
            
            # Make concurrent requests
            concurrent_results = await asyncio.gather(*[
                self.client.get_issue(key) for key in issue_keys
            ], return_exceptions=True)
            
            end_time = time.time()
            response_time = (end_time - start_time) * 1000
            
            successful = sum(1 for r in concurrent_results if not isinstance(r, Exception))
            
            result.update({
                "status": "healthy" if successful == len(issue_keys) else "degraded",
                "response_time_ms": round(response_time, 2),
                "details": {
                    "requests_made": len(issue_keys),
                    "successful_requests": successful,
                    "failed_requests": len(issue_keys) - successful
                }
            })
            
        except Exception as e:
            result.update({
                "status": "unhealthy",
                "error": str(e)
            })
        
        return result
    
    async def check_rate_limiting(self) -> Dict[str, Any]:
        """Test rate limiting behavior."""
        result = {
            "test": "rate_limiting",
            "status": "unknown",
            "response_time_ms": 0,
            "details": {}
        }
        
        try:
            start_time = time.time()
            
            # Make several rapid requests to test rate limiting
            tasks = [
                self.client._make_request('GET', '/rest/api/2/myself')
                for _ in range(5)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            end_time = time.time()
            response_time = (end_time - start_time) * 1000
            
            successful = sum(1 for r in results if not isinstance(r, Exception))
            rate_limited = sum(1 for r in results if isinstance(r, Exception) and "429" in str(r))
            
            result.update({
                "status": "healthy",
                "response_time_ms": round(response_time, 2),
                "details": {
                    "requests_made": len(tasks),
                    "successful_requests": successful,
                    "rate_limited_requests": rate_limited,
                    "rate_limiting_working": rate_limited > 0 or successful == len(tasks)
                }
            })
            
        except Exception as e:
            result.update({
                "status": "unhealthy",
                "error": str(e)
            })
        
        return result
    
    async def check_memory_usage(self) -> Dict[str, Any]:
        """Check memory usage (basic)."""
        result = {
            "test": "memory_usage",
            "status": "healthy",
            "details": {}
        }
        
        try:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            
            result["details"] = {
                "rss_mb": round(memory_info.rss / 1024 / 1024, 2),
                "vms_mb": round(memory_info.vms / 1024 / 1024, 2),
                "cpu_percent": process.cpu_percent()
            }
            
            # Flag if memory usage is high (>500MB)
            if memory_info.rss > 500 * 1024 * 1024:
                result["status"] = "warning"
                result["details"]["warning"] = "High memory usage detected"
                
        except ImportError:
            result["details"]["note"] = "psutil not available for memory monitoring"
        except Exception as e:
            result.update({
                "status": "error",
                "error": str(e)
            })
        
        return result
    
    async def run_all_checks(self) -> Dict[str, Any]:
        """Run all health checks."""
        print("🏥 Running JIRA MCP Server Health Checks")
        print("=" * 50)
        
        overall_result = {
            "timestamp": time.time(),
            "server_url": self.server_url,
            "max_concurrent_requests": self.max_concurrent,
            "checks": [],
            "summary": {
                "total_checks": 0,
                "healthy": 0,
                "degraded": 0,
                "unhealthy": 0,
                "skipped": 0
            }
        }
        
        # List of checks to run
        checks = [
            ("🔗 Connectivity", self.check_connectivity),
            ("🔍 Search Performance", self.check_search_performance),
            ("⚡ Concurrent Performance", self.check_concurrent_performance),
            ("🚦 Rate Limiting", self.check_rate_limiting),
            ("💾 Memory Usage", self.check_memory_usage),
        ]
        
        for check_name, check_func in checks:
            print(f"\n{check_name}...")
            
            try:
                check_result = await check_func()
                overall_result["checks"].append(check_result)
                
                status = check_result["status"]
                overall_result["summary"]["total_checks"] += 1
                overall_result["summary"][status] += 1
                
                # Print result
                status_emoji = {
                    "healthy": "✅",
                    "degraded": "⚠️",
                    "unhealthy": "❌",
                    "skipped": "⏭️",
                    "warning": "⚠️",
                    "error": "❌"
                }.get(status, "❓")
                
                print(f"  {status_emoji} {status.upper()}")
                
                if "response_time_ms" in check_result and check_result["response_time_ms"] > 0:
                    print(f"  ⏱️  Response time: {check_result['response_time_ms']}ms")
                
                if "error" in check_result:
                    print(f"  ❌ Error: {check_result['error']}")
                
                if "details" in check_result and check_result["details"]:
                    for key, value in check_result["details"].items():
                        if key != "warning":
                            print(f"  📊 {key}: {value}")
                
            except Exception as e:
                print(f"  ❌ Check failed: {e}")
                overall_result["checks"].append({
                    "test": check_name,
                    "status": "error",
                    "error": str(e)
                })
                overall_result["summary"]["total_checks"] += 1
                overall_result["summary"]["unhealthy"] += 1
        
        return overall_result
    
    def print_summary(self, results: Dict[str, Any]):
        """Print health check summary."""
        print(f"\n📊 Health Check Summary")
        print("=" * 30)
        
        summary = results["summary"]
        total = summary["total_checks"]
        
        print(f"Total Checks: {total}")
        print(f"✅ Healthy: {summary['healthy']}")
        print(f"⚠️  Degraded: {summary['degraded']}")
        print(f"❌ Unhealthy: {summary['unhealthy']}")
        print(f"⏭️  Skipped: {summary['skipped']}")
        
        # Overall health status
        if summary["unhealthy"] > 0:
            overall_status = "❌ UNHEALTHY"
        elif summary["degraded"] > 0:
            overall_status = "⚠️  DEGRADED"
        elif summary["healthy"] == total:
            overall_status = "✅ HEALTHY"
        else:
            overall_status = "❓ UNKNOWN"
        
        print(f"\nOverall Status: {overall_status}")
        
        # Recommendations
        print(f"\n💡 Recommendations:")
        if summary["unhealthy"] > 0:
            print("  • Check JIRA credentials and network connectivity")
            print("  • Review error logs for specific issues")
        elif summary["degraded"] > 0:
            print("  • Monitor performance and consider adjusting rate limits")
        else:
            print("  • System is operating normally")
        
        print("  • Run 'python check_rate_limits.py' for detailed rate limit analysis")
        print("  • Monitor logs in 'jira_mcp_server.log' for ongoing issues")

async def main():
    """Run health checks."""
    if not os.getenv("JIRA_SERVER_URL") or not os.getenv("JIRA_API_TOKEN"):
        print("""
❌ Missing JIRA credentials!

Please create a .env file with:
JIRA_SERVER_URL=https://your-company.atlassian.net
JIRA_API_TOKEN=your_api_token_here
""")
        sys.exit(1)
    
    checker = HealthChecker()
    
    try:
        await checker.initialize()
        results = await checker.run_all_checks()
        checker.print_summary(results)
        
        # Save results to file
        with open('health_check_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n📄 Detailed results saved to: health_check_results.json")
        
        # Exit with appropriate code
        if results["summary"]["unhealthy"] > 0:
            sys.exit(1)
        elif results["summary"]["degraded"] > 0:
            sys.exit(2)
        else:
            sys.exit(0)
            
    except Exception as e:
        print(f"\n❌ Health check failed: {e}")
        sys.exit(1)
    finally:
        await checker.cleanup()

if __name__ == "__main__":
    asyncio.run(main()) 
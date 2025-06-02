#!/usr/bin/env python3
"""
Test MCP protocol communication directly.
This script tests the JSON protocol communication to identify any parsing issues.
"""
import json
import subprocess
import sys
import time

def test_mcp_protocol():
    """Test MCP protocol communication."""
    print("🧪 Testing MCP Protocol Communication")
    print("=" * 40)
    
    try:
        # Start the MCP server
        print("📋 Starting MCP server...")
        process = subprocess.Popen(
            [sys.executable, "jira_mcp_server.py"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Give it a moment to start
        time.sleep(1)
        
        # Send initialize request
        print("📡 Sending initialize request...")
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }
        
        # Send the request
        request_json = json.dumps(init_request) + "\n"
        process.stdin.write(request_json)
        process.stdin.flush()
        
        # Read response with timeout
        print("📥 Reading response...")
        response_line = process.stdout.readline()
        
        if response_line:
            print(f"✅ Received response: {len(response_line)} characters")
            print(f"📄 Response preview: {response_line[:100]}...")
            
            # Try to parse JSON
            try:
                response_data = json.loads(response_line)
                print("✅ JSON parsing successful")
                print(f"📊 Response ID: {response_data.get('id')}")
                print(f"📊 Response method: {response_data.get('result', {}).get('capabilities', 'N/A')}")
            except json.JSONDecodeError as e:
                print(f"❌ JSON parsing failed: {e}")
                print(f"📄 Raw response: {repr(response_line)}")
                return False
        else:
            print("❌ No response received")
            return False
        
        # Clean shutdown
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        
        print("✅ MCP protocol test completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ MCP protocol test failed: {e}")
        if 'process' in locals():
            try:
                process.terminate()
                process.wait(timeout=2)
            except:
                process.kill()
        return False

if __name__ == "__main__":
    success = test_mcp_protocol()
    if success:
        print("\n🎉 MCP protocol is working correctly!")
    else:
        print("\n❌ MCP protocol has issues that need to be fixed.") 
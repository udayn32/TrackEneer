#!/usr/bin/env python
"""Test the live Quote API endpoint"""

import asyncio
import aiohttp

async def test_quote_endpoint():
    """Test the /api/quote endpoint"""
    print("=" * 60)
    print("Testing FastAPI /api/quote endpoint")
    print("=" * 60)
    print("\n⚠️  Make sure the FastAPI server is running on localhost:5000")
    print("   Run: uvicorn scheduler:app --reload\n")
    
    base_url = "http://localhost:5000"
    modules = ["study", "placement", "schedule", None]  # None = no module param
    
    async with aiohttp.ClientSession() as session:
        for module in modules:
            try:
                if module:
                    url = f"{base_url}/api/quote?module={module}"
                    print(f"\n🔍 Testing: GET {url}")
                else:
                    url = f"{base_url}/api/quote"
                    print(f"\n🔍 Testing: GET {url} (no module)")
                
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    print(f"📊 Status: {resp.status}")
                    
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"✅ Success!")
                        print(f"📝 Quote: \"{data.get('content', '')}\"")
                        print(f"👤 Author: {data.get('author', 'Unknown')}")
                        print(f"🔧 Source: {data.get('source', 'unknown')}")
                        if 'module' in data:
                            print(f"📚 Module: {data.get('module', 'N/A')}")
                    else:
                        text = await resp.text()
                        print(f"❌ Failed: {text}")
                        
            except aiohttp.ClientConnectorError:
                print(f"❌ Error: Cannot connect to FastAPI server at {base_url}")
                print(f"   Please start the server first with: uvicorn scheduler:app --reload")
                return False
            except Exception as e:
                print(f"❌ Error: {e}")
    
    return True

if __name__ == "__main__":
    print("\n🚀 Live API Test\n")
    asyncio.run(test_quote_endpoint())
    
    print("\n" + "=" * 60)
    print("NEXT STEPS:")
    print("=" * 60)
    print("1. If server is not running, start it:")
    print("   cd server")
    print("   uvicorn scheduler:app --reload")
    print("\n2. Run this test again:")
    print("   python test_live_api.py")
    print("=" * 60)

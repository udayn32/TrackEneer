#!/usr/bin/env python
"""Debug script to test quote API functionality"""

import asyncio
import aiohttp

async def test_quotable_api():
    """Test Quotable API"""
    print("=" * 60)
    print("Testing Quotable API")
    print("=" * 60)
    
    try:
        async with aiohttp.ClientSession() as session:
            url = 'https://api.quotable.io/random'
            print(f"🔍 Fetching: {url}")
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                print(f"📊 Status Code: {resp.status}")
                
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ Success!")
                    print(f"📝 Quote: \"{data.get('content', '')}\"")
                    print(f"👤 Author: {data.get('author', 'Unknown')}")
                    print(f"🏷️  Tags: {data.get('tags', [])}")
                    return True
                else:
                    print(f"❌ Failed with status {resp.status}")
                    return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

async def test_quotable_with_tags():
    """Test Quotable API with tags"""
    print("\n" + "=" * 60)
    print("Testing Quotable API with Tags (learning)")
    print("=" * 60)
    
    try:
        async with aiohttp.ClientSession() as session:
            url = 'https://api.quotable.io/random?tags=learning,knowledge,education'
            print(f"🔍 Fetching: {url}")
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                print(f"📊 Status Code: {resp.status}")
                
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ Success!")
                    print(f"📝 Quote: \"{data.get('content', '')}\"")
                    print(f"👤 Author: {data.get('author', 'Unknown')}")
                    print(f"🏷️  Tags: {data.get('tags', [])}")
                    return True
                else:
                    print(f"❌ Failed with status {resp.status}")
                    return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

async def test_zenquotes_api():
    """Test Zenquotes API"""
    print("\n" + "=" * 60)
    print("Testing Zenquotes API")
    print("=" * 60)
    
    try:
        async with aiohttp.ClientSession() as session:
            url = 'https://zenquotes.io/api/random'
            print(f"🔍 Fetching: {url}")
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                print(f"📊 Status Code: {resp.status}")
                
                if resp.status == 200:
                    data = await resp.json()
                    if data and isinstance(data, list) and len(data) > 0:
                        quote = data[0]
                        print(f"✅ Success!")
                        print(f"📝 Quote: \"{quote.get('q', '')}\"")
                        print(f"👤 Author: {quote.get('a', 'Unknown')}")
                        return True
                    else:
                        print(f"❌ Empty or invalid response")
                        return False
                else:
                    print(f"❌ Failed with status {resp.status}")
                    return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

async def test_scheduler_quote_function():
    """Test the actual function from scheduler.py"""
    print("\n" + "=" * 60)
    print("Testing scheduler.py _fetch_external_quote_api() function")
    print("=" * 60)
    
    try:
        # Import the function
        import sys
        import os
        sys.path.insert(0, os.path.dirname(__file__))
        
        # Import after path setup
        from scheduler import _fetch_external_quote_api
        
        print("🔍 Calling _fetch_external_quote_api() with tags=['learning']")
        result = await _fetch_external_quote_api(tags=['learning', 'knowledge'])
        
        if result:
            print(f"✅ Function returned a quote!")
            print(f"📝 Content: \"{result.get('content', '')}\"")
            print(f"👤 Author: {result.get('author', 'Unknown')}")
            print(f"🔧 Source: {result.get('source', 'unknown')}")
            if 'tags' in result:
                print(f"🏷️  Tags: {result.get('tags', [])}")
            return True
        else:
            print(f"❌ Function returned None (both APIs failed)")
            return False
    except Exception as e:
        print(f"❌ Error testing scheduler function: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all tests"""
    print("\n" + "🧪" * 30)
    print("QUOTE API DEBUG TEST SUITE")
    print("🧪" * 30 + "\n")
    
    results = []
    
    # Test 1: Quotable API
    results.append(("Quotable API", await test_quotable_api()))
    
    # Test 2: Quotable with tags
    results.append(("Quotable API (with tags)", await test_quotable_with_tags()))
    
    # Test 3: Zenquotes API
    results.append(("Zenquotes API", await test_zenquotes_api()))
    
    # Test 4: Scheduler function
    results.append(("Scheduler Function", await test_scheduler_quote_function()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    print(f"\n📊 Results: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("🎉 All tests passed! Quote API is working correctly.")
    elif passed_count > 0:
        print("⚠️  Some tests failed. Check the output above for details.")
    else:
        print("❌ All tests failed. Check your internet connection and API availability.")

if __name__ == "__main__":
    asyncio.run(main())

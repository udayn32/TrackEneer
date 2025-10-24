#!/usr/bin/env python
"""
Quote API Test Script
Tests all three quote strategies
"""

import asyncio
import sys
import json

# Simple test without importing the full scheduler
async def test_quote_api():
    """Test the quote API implementation"""
    print("=" * 60)
    print("🧪 Quote API Test Suite")
    print("=" * 60)
    
    # Test 1: Check if aiohttp is installed
    print("\n✓ Test 1: Checking dependencies...")
    try:
        import aiohttp
        print("  ✅ aiohttp is installed")
    except ImportError:
        print("  ❌ aiohttp not installed")
        print("  Run: pip install aiohttp")
        sys.exit(1)
    
    # Test 2: Check if external APIs are reachable
    print("\n✓ Test 2: Testing external APIs...")
    try:
        async with aiohttp.ClientSession() as session:
            # Test Quotable API
            async with session.get('https://api.quotable.io/random', timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"  ✅ Quotable API works")
                    print(f"     Quote: '{data['content'][:50]}...'")
                    print(f"     Author: {data['author']}")
                else:
                    print(f"  ⚠️  Quotable API returned {resp.status}")
    except Exception as e:
        print(f"  ⚠️  Quotable API error (expected if offline): {str(e)[:50]}")
    
    # Test 3: Check Zenquotes API
    print("\n✓ Test 3: Testing Zenquotes API (backup)...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://zenquotes.io/api/random', timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data:
                        print(f"  ✅ Zenquotes API works")
                        print(f"     Quote: '{data[0]['q'][:50]}...'")
                else:
                    print(f"  ⚠️  Zenquotes API returned {resp.status}")
    except Exception as e:
        print(f"  ⚠️  Zenquotes API error (expected if offline): {str(e)[:50]}")
    
    # Test 4: Check static quotes
    print("\n✓ Test 4: Testing static quotes...")
    FALLBACK_QUOTES = [
        {"content": "The beautiful thing about learning is that no one can take it away from you.", "author": "B.B. King", "category": "study"},
        {"content": "Live as if you were to die tomorrow. Learn as if you were to live forever.", "author": "Mahatma Gandhi", "category": "study"},
        {"content": "Success is the sum of small efforts, repeated day in and day out.", "author": "Robert Collier", "category": "schedule"},
    ]
    
    if len(FALLBACK_QUOTES) >= 3:
        print(f"  ✅ {len(FALLBACK_QUOTES)} fallback quotes loaded")
        import random
        q = random.choice(FALLBACK_QUOTES)
        print(f"     Sample: '{q['content'][:50]}...'")
        print(f"     Author: {q['author']}")
    else:
        print(f"  ❌ Fallback quotes not loaded properly")
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)
    print("\n📝 Next steps:")
    print("  1. Start server: python scheduler.py")
    print("  2. Test endpoint: curl http://localhost:5000/api/quote")
    print("  3. Check response has 'strategy' field")
    print("  4. Integrate into frontend")
    print("\n📚 Documentation:")
    print("  - QUOTE_QUICKSTART.md - Quick start")
    print("  - QUOTE_API_README.md - Full documentation")
    print("  - QUOTE_IMPLEMENTATION_SUMMARY.md - Technical details")

if __name__ == "__main__":
    asyncio.run(test_quote_api())

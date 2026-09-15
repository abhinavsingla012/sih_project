#!/usr/bin/env python3
"""
Temporary debug script to test Origin header behavior
"""
import asyncio
import httpx
import os
from dotenv import load_dotenv

load_dotenv('/app/backend/.env.local')

async def test_origin_scenarios():
    base_url = os.getenv('APP_ORIGIN', 'https://txn-orchestrate.preview.emergentagent.com')
    api_url = f"{base_url}/api/auth/login"
    
    print("=" * 80)
    print("TESTING ORIGIN HEADER SCENARIOS")
    print("=" * 80)
    print(f"API URL: {api_url}")
    print(f"Expected APP_ORIGIN: {base_url}")
    print()
    
    test_cases = [
        ("No Origin header", {}),
        ("Correct Origin", {"origin": base_url}),
        ("Empty Origin", {"origin": ""}),
        ("Wrong Origin", {"origin": "https://evil.com"}),
    ]
    
    credentials = {
        "email": "operator@demo.in",
        "password": "Demo@2026!"
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for name, headers in test_cases:
            print(f"\n{'='*60}")
            print(f"Test: {name}")
            print(f"Headers: {headers}")
            print("-" * 60)
            
            try:
                response = await client.post(
                    api_url,
                    json=credentials,
                    headers=headers,
                    follow_redirects=False
                )
                
                print(f"Status: {response.status_code}")
                print(f"Response: {response.text[:200]}")
                
                if response.status_code == 403:
                    print("❌ ORIGIN_DENIED")
                elif response.status_code == 200:
                    print("✅ SUCCESS")
                else:
                    print(f"⚠️  Unexpected status: {response.status_code}")
                    
            except Exception as e:
                print(f"❌ Error: {e}")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    asyncio.run(test_origin_scenarios())

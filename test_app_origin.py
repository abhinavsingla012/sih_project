#!/usr/bin/env python3
"""
Debug script to check APP_ORIGIN value
"""
import sys
sys.path.insert(0, '/app/backend')

from core.config import setting

print("=" * 80)
print("CHECKING APP_ORIGIN CONFIGURATION")
print("=" * 80)

app_origin = setting('APP_ORIGIN')
print(f"APP_ORIGIN value: '{app_origin}'")
print(f"APP_ORIGIN type: {type(app_origin)}")
print(f"APP_ORIGIN length: {len(app_origin)}")
print(f"APP_ORIGIN repr: {repr(app_origin)}")
print(f"APP_ORIGIN bytes: {app_origin.encode('utf-8')}")

test_origin = "https://txn-orchestrate.preview.emergentagent.com"
print(f"\nTest origin: '{test_origin}'")
print(f"Test origin type: {type(test_origin)}")
print(f"Test origin length: {len(test_origin)}")

print(f"\nComparison:")
print(f"  app_origin == test_origin: {app_origin == test_origin}")
print(f"  test_origin in (None, app_origin): {test_origin in (None, app_origin)}")
print(f"  test_origin not in (None, app_origin): {test_origin not in (None, app_origin)}")

# Check for hidden characters
print(f"\nChecking for hidden characters:")
for i, char in enumerate(app_origin):
    print(f"  [{i}] {repr(char)} (ord: {ord(char)})")

print("=" * 80)

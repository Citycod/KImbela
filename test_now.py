#!/usr/bin/env python3
import requests
import json

BASE_URL = "http://localhost:5000"

print("🚀 Testing Kimbela Server...")
print("=" * 50)

# Test 1: Home page
print("1. Testing home page...")
try:
    response = requests.get(BASE_URL + "/", timeout=5)
    print(f"   ✅ Status: {response.status_code}")
    if response.status_code == 200:
        print("   📄 Home page loaded successfully")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 2: Security - blocked paths
print("\n2. Testing security (blocked paths)...")
blocked_paths = ["/.env", "/.git/config", "/wp-admin"]
for path in blocked_paths:
    try:
        response = requests.get(BASE_URL + path, timeout=3)
        if response.status_code in [404, 403]:
            print(f"   ✅ {path}: {response.status_code} (blocked)")
        else:
            print(f"   ⚠️ {path}: {response.status_code} (not blocked)")
    except Exception as e:
        print(f"   ❌ {path}: Error - {e}")

# Test 3: WebSocket test page
print("\n3. Testing WebSocket endpoint...")
try:
    response = requests.get(BASE_URL + "/socket-test", timeout=5)
    if response.status_code == 200:
        print("   ✅ WebSocket test page accessible")
        # Check content
        if "socket.io" in response.text:
            print("   ✅ Socket.IO library loaded")
    else:
        print(f"   ❌ WebSocket test: {response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 4: Test messaging endpoint
print("\n4. Testing messaging endpoint...")
try:
    response = requests.get(BASE_URL + "/test-messaging", timeout=5)
    if response.status_code == 200:
        print("   ✅ Messaging test page accessible")
    elif response.status_code == 302:  # Redirect to login
        print("   🔒 Messaging test requires login (redirected)")
    else:
        print(f"   ⚠️ Messaging test: {response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 5: Check API endpoints
print("\n5. Testing API endpoints...")
api_endpoints = [
    ("/api/messaging/friends", "GET"),
    ("/api/messaging/send", "POST"),
    ("/get_user_groups", "GET"),
]

for endpoint, method in api_endpoints:
    try:
        if method == "GET":
            response = requests.get(BASE_URL + endpoint, timeout=3)
        else:
            response = requests.post(BASE_URL + endpoint, timeout=3, json={})

        if response.status_code == 401 or response.status_code == 302:
            print(f"   🔒 {endpoint}: {response.status_code} (requires auth)")
        elif response.status_code == 405:
            print(f"   ⚠️ {endpoint}: {response.status_code} (method not allowed)")
        else:
            print(f"   📡 {endpoint}: {response.status_code}")
    except Exception as e:
        print(f"   ❌ {endpoint}: Error - {e}")

# Test 6: Rate limiting test
print("\n6. Testing rate limiting...")
print("   (Making multiple quick requests to /user_dashboard)")
status_codes = []
for i in range(12):
    try:
        response = requests.get(BASE_URL + "/user_dashboard", timeout=2)
        status_codes.append(response.status_code)
        if response.status_code == 429:
            print(f"   ✅ Rate limit triggered after {i + 1} requests!")
            break
    except Exception as e:
        status_codes.append(f"E:{str(e)[:20]}")

if 429 not in status_codes:
    print(f"   ⚠️ Rate limit not triggered. Statuses: {set(status_codes)}")

print("\n" + "=" * 50)
print("✅ Server is running!")
print("💡 Open http://localhost:5000 in your browser")
print("💡 Test WebSocket: http://localhost:5000/socket-test")
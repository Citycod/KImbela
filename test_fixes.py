#!/usr/bin/env python3
import requests
import time

BASE_URL = "http://localhost:5000"


def test_security():
    print("Testing security features...")

    # Test blocked paths
    blocked_paths = ["/.env", "/.git/config", "/wp-admin", "/phpmyadmin"]
    for path in blocked_paths:
        response = requests.get(BASE_URL + path)
        print(f"  {path}: {response.status_code} (expected: 404)")

    # Test rate limiting
    print("\nTesting rate limiting...")
    for i in range(15):
        response = requests.get(BASE_URL + "/user_dashboard")
        print(f"  Request {i + 1}: {response.status_code}")
        if response.status_code == 429:
            print("  ✅ Rate limiting works!")
            break
        time.sleep(0.1)

    # Test WebSocket endpoint
    print("\nTesting WebSocket endpoint...")
    response = requests.get(BASE_URL + "/socket-test")
    if response.status_code == 200:
        print("  ✅ WebSocket test page accessible")
    else:
        print(f"  ❌ WebSocket test failed: {response.status_code}")


def test_performance():
    print("\nTesting performance endpoints...")

    # Test get_user_groups (should be cached)
    start = time.time()
    response = requests.get(BASE_URL + "/get_user_groups")
    elapsed = time.time() - start

    print(f"  First request to /get_user_groups: {elapsed:.2f}s")

    # Second request should be faster (cached)
    start = time.time()
    response = requests.get(BASE_URL + "/get_user_groups")
    elapsed = time.time() - start
    print(f"  Second request (cached): {elapsed:.2f}s")


if __name__ == "__main__":
    print("=" * 50)
    print("Kimbela Security & Performance Test")
    print("=" * 50)

    test_security()
    test_performance()

    print("\n" + "=" * 50)
    print("Tests completed!")
    print("=" * 50)
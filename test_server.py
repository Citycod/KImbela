#!/usr/bin/env python3
import requests
import time
import socket


def check_server(port=5000, timeout=5):
    """Check if server is running and responding"""
    try:
        response = requests.get(f"http://localhost:{port}/", timeout=timeout)
        print(f"✅ Server is running: HTTP {response.status_code}")
        return True
    except requests.exceptions.ConnectionError:
        print(f"❌ Server not running on port {port}")
        return False
    except Exception as e:
        print(f"⚠️ Error checking server: {e}")
        return False


def test_security_features():
    """Test security features"""
    print("\n🔒 Testing Security Features:")
    print("-" * 40)

    base_url = "http://localhost:5000"

    # Test 1: Check main page
    try:
        response = requests.get(base_url, timeout=3)
        if response.status_code == 200:
            print("✅ Main page accessible")
        else:
            print(f"⚠️ Main page: {response.status_code}")
    except Exception as e:
        print(f"❌ Cannot access server: {e}")
        return

    # Test 2: Test blocked paths
    print("\n🛡️ Testing blocked paths (should return 404):")
    test_paths = [
        "/.env",
        "/.git/config",
        "/wp-admin",
        "/phpmyadmin",
        "/test-messaging",  # Your existing test route
        "/socket-test",  # Your existing WebSocket test
    ]

    for path in test_paths:
        try:
            response = requests.get(base_url + path, timeout=3)
            if response.status_code == 404:
                print(f"  ✅ {path}: 404 (correctly blocked)")
            elif response.status_code == 403:
                print(f"  ✅ {path}: 403 (access denied)")
            elif response.status_code == 200:
                print(f"  📍 {path}: 200 (accessible)")
            else:
                print(f"  ⚠️ {path}: {response.status_code}")
        except Exception as e:
            print(f"  ❌ {path}: Error - {e}")

    # Test 3: Test WebSocket endpoint
    print("\n🔌 Testing WebSocket endpoint:")
    try:
        response = requests.get(base_url + "/socket-test", timeout=5)
        if response.status_code == 200:
            print("✅ WebSocket test page accessible")
            # Check if it contains Socket.IO script
            if "socket.io" in response.text.lower():
                print("✅ Socket.IO script included")
        else:
            print(f"⚠️ WebSocket test: {response.status_code}")
    except Exception as e:
        print(f"❌ WebSocket test error: {e}")


def test_rate_limiting():
    """Test if rate limiting is working"""
    print("\n⏱️ Testing rate limiting:")

    base_url = "http://localhost:5000"

    # Try accessing user_dashboard multiple times quickly
    print("  Testing /user_dashboard rate limit...")
    status_codes = []

    for i in range(15):
        try:
            response = requests.get(base_url + "/user_dashboard", timeout=2)
            status_codes.append(response.status_code)
            if response.status_code == 429:
                print(f"  ✅ Rate limiting triggered after {i + 1} requests")
                break
        except Exception as e:
            status_codes.append(str(e))

    if 429 not in status_codes:
        print("  ⚠️ Rate limiting not triggered (Redis may not be available)")

    print(f"  Status codes: {status_codes}")


def check_database():
    """Check database connectivity"""
    print("\n🗄️ Checking database:")
    try:
        from app_config import app
        from extensions import db

        with app.app_context():
            # Try a simple query
            result = db.session.execute("SELECT 1")
            print("✅ Database connection successful")

            # Check some table counts
            tables_to_check = ['users', 'groups', 'messages', 'posts', 'notifications']
            for table in tables_to_check:
                try:
                    count = db.session.execute(f"SELECT COUNT(*) FROM {table}").scalar()
                    print(f"  {table}: {count} rows")
                except:
                    print(f"  {table}: Table not found")

    except Exception as e:
        print(f"❌ Database error: {e}")


def main():
    print("=" * 60)
    print("KIMBELA SERVER DIAGNOSTIC TOOL")
    print("=" * 60)

    # Check if server is running
    if not check_server():
        print("\n💡 Server not running. Please start it with:")
        print("   python runserver.py")
        print("   OR")
        print("   docker-compose up -d")
        return

    # Run tests
    test_security_features()
    test_rate_limiting()
    check_database()

    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60)
    print("\nRecommendations:")
    print("1. Fix Redis connection or use memory storage")
    print("2. Update database indexes to match your schema")
    print("3. Test WebSocket connections manually")
    print("\nQuick tests:")
    print("  curl http://localhost:5000/")
    print("  curl http://localhost:5000/.env")
    print("  curl http://localhost:5000/socket-test")


if __name__ == "__main__":
    main()
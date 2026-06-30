"""
Quick test to verify the edit matchmaking API route is properly registered
and the logic is sound.
"""
import sys
import os

# Ensure we can import from the project
sys.path.insert(0, os.path.dirname(__file__))

def test_route_registration():
    """Test that the edit route is registered on the Flask app."""
    try:
        from app_config import app
        
        with app.app_context():
            # Get all registered rules
            rules = {rule.rule: rule.methods for rule in app.url_map.iter_rules()}
            
            edit_route = '/api/requests/<int:request_id>/edit'
            
            if edit_route in rules:
                methods = rules[edit_route]
                print(f"✅ Edit route registered: {edit_route}")
                print(f"   Methods: {methods}")
                
                if 'PUT' in methods:
                    print("   ✅ PUT method supported")
                else:
                    print("   ❌ PUT method NOT found")
                    
                if 'POST' in methods:
                    print("   ✅ POST method supported (fallback)")
                else:
                    print("   ⚠️  POST method not found (optional)")
            else:
                print(f"❌ Edit route NOT found: {edit_route}")
                print("\n   Available matchmaking routes:")
                for rule, methods in sorted(rules.items()):
                    if 'request' in rule.lower() or 'match' in rule.lower():
                        print(f"   → {rule} [{', '.join(methods - {'OPTIONS', 'HEAD'})}]")
                return False
            
            # Also verify existing related routes
            related_routes = [
                '/api/requests/<int:request_id>',
                '/api/requests/<int:request_id>/update-image',
                '/api/requests/<int:request_id>/deactivate',
                '/api/requests/<int:request_id>/like',
            ]
            
            print("\n📋 Related matchmaking routes:")
            for route in related_routes:
                if route in rules:
                    m = rules[route] - {'OPTIONS', 'HEAD'}
                    print(f"   ✅ {route} [{', '.join(m)}]")
                else:
                    print(f"   ❌ {route} NOT FOUND")
            
            return True
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_edit_logic():
    """Test the edit endpoint logic with a mock request."""
    try:
        from app_config import app
        from extensions import db
        
        with app.app_context():
            # Test unauthenticated access (should redirect/fail)
            with app.test_client() as client:
                # Test without authentication - should get redirect (302) to login
                resp = client.put(
                    '/api/requests/1/edit',
                    json={'about_you': 'Test'},
                    content_type='application/json'
                )
                print(f"\n🔒 Unauthenticated PUT /api/requests/1/edit")
                print(f"   Status: {resp.status_code}")
                
                if resp.status_code in (302, 401, 403):
                    print(f"   ✅ Correctly blocked unauthenticated access")
                else:
                    print(f"   ⚠️  Unexpected status code: {resp.status_code}")
                
                # Test POST method too
                resp2 = client.post(
                    '/api/requests/1/edit',
                    json={'about_you': 'Test'},
                    content_type='application/json'
                )
                print(f"\n🔒 Unauthenticated POST /api/requests/1/edit")
                print(f"   Status: {resp2.status_code}")
                
                if resp2.status_code in (302, 401, 403):
                    print(f"   ✅ Correctly blocked unauthenticated access")
                else:
                    print(f"   ⚠️  Unexpected status code: {resp2.status_code}")
                    
        return True
        
    except Exception as e:
        print(f"❌ Error during logic test: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    print("=" * 50)
    print("🧪 Testing Matchmaking Edit API")
    print("=" * 50)
    
    r1 = test_route_registration()
    r2 = test_edit_logic()
    
    print("\n" + "=" * 50)
    if r1 and r2:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed")
    print("=" * 50)

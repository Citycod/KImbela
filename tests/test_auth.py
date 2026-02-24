def test_login_success_redirects(client, login):
    response = login()
    assert response.status_code == 302
    assert "/user_dashboard" in response.headers.get("Location", "")


def test_login_failure(client):
    response = client.post(
        "/login",
        data={"email": "nope@example.com", "password": "wrong"},
        follow_redirects=False,
    )
    assert response.status_code == 200


def test_dashboard_requires_login(client):
    response = client.get("/user_dashboard", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers.get("Location", "")

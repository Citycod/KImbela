def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200


def test_404(client):
    response = client.get("/this-route-should-not-exist")
    assert response.status_code == 404


def test_socket_test_page(client):
    response = client.get("/socket-test")
    assert response.status_code == 200


def test_uploads_requires_login(client):
    response = client.get("/uploads/somefile.png")
    assert response.status_code in (302, 401)


def test_debug_routes_disabled_by_default(client):
    response = client.get("/debug/requests")
    assert response.status_code == 404

def test_messaging_friends_requires_login(client):
    response = client.get("/api/messaging/friends")
    assert response.status_code in (302, 401)


def test_messaging_friends_empty_after_login(client, login):
    login()
    response = client.get("/api/messaging/friends")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["friends"] == []


def test_messaging_upload_missing_file(client, login):
    login()
    response = client.post("/api/messaging/upload", data={"to_id": 1, "type": "image"})
    assert response.status_code == 400

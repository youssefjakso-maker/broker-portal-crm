def test_post_without_csrf_token_is_rejected(app_client):
    response = app_client.post("/login", data={"email": "a@b.c", "password": "x"})
    assert response.status_code == 400


def test_login_page_renders(app_client):
    response = app_client.get("/login")
    assert response.status_code == 200
    assert b"<form" in response.data

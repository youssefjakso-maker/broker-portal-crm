def test_dashboard_renders(admin_client, live_version):
    response = admin_client.get("/dashboard")
    assert response.status_code == 200


def test_projects_renders(admin_client, live_version):
    response = admin_client.get("/projects")
    assert response.status_code == 200
    assert b"<html" in response.data.lower()

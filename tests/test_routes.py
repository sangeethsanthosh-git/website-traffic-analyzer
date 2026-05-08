from pathlib import Path

from app import create_app


def test_dashboard_redirects_to_login_when_signed_out(tmp_path: Path):
    app = create_app({"TESTING": True, "DATABASE_PATH": tmp_path / "test.db"})
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_login_page_renders(tmp_path: Path):
    app = create_app({"TESTING": True, "DATABASE_PATH": tmp_path / "test.db"})
    client = app.test_client()

    response = client.get("/login")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Sign in to open the traffic dashboard." in text
    assert "data/app.db" in text


def test_register_then_view_dashboard(tmp_path: Path):
    app = create_app({"TESTING": True, "DATABASE_PATH": tmp_path / "test.db"})
    client = app.test_client()

    response = client.post(
        "/login",
        data={"action": "register", "username": "demo_user", "password": "secret1"},
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Account created successfully. You are now signed in." in text
    assert "Traffic Intelligence Dashboard" in text
    assert "demo_user" in text


def test_existing_user_can_log_in(tmp_path: Path):
    app = create_app({"TESTING": True, "DATABASE_PATH": tmp_path / "test.db"})
    client = app.test_client()

    client.post(
        "/login",
        data={"action": "register", "username": "returning_user", "password": "secret1"},
        follow_redirects=True,
    )
    client.post("/logout", follow_redirects=True)

    response = client.post(
        "/login",
        data={"action": "login", "username": "returning_user", "password": "secret1"},
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Welcome back." in text
    assert "Traffic Intelligence Dashboard" in text

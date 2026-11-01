from __future__ import annotations

from conftest import PASSWORD

from mla_api.models import AuditEvent, AuthSession


def test_register_logs_in_and_creates_owned_org(api):
    me = api.register("ana@example.com", org="Auto Peças Ana")
    assert me["user"]["email"] == "ana@example.com"
    assert [(m["organization"]["name"], m["role"]) for m in me["memberships"]] == [("Auto Peças Ana", "owner")]
    assert me["memberships"][0]["organization"]["slug"] == "auto-pecas-ana"
    assert api.get("/api/auth/me").status_code == 200


def test_session_cookie_is_httponly_and_token_not_stored_in_clear(api, app):
    r = api.post("/api/auth/register", json={"name": "A", "email": "a@example.com", "password": PASSWORD,
                                             "organization_name": "X"})
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    token = api.cookies.get("mla_session")
    with app.state.sessionmaker() as db:
        hashes = [s.token_hash for s in db.query(AuthSession).all()]
    assert token not in hashes and len(hashes[0]) == 64


def test_duplicate_email_and_weak_password_refused(api):
    api.register("a@example.com")
    r = api.post("/api/auth/register", json={"name": "B", "email": "A@example.com", "password": PASSWORD,
                                             "organization_name": "Y"})
    assert r.status_code == 409
    r = api.post("/api/auth/register", json={"name": "B", "email": "b@example.com", "password": "curta",
                                             "organization_name": "Y"})
    assert r.status_code == 422


def test_login_logout(new_api):
    a = new_api()
    a.register("a@example.com")
    b = new_api()
    assert b.get("/api/auth/me").status_code == 401
    assert b.post("/api/auth/login", json={"email": "a@example.com", "password": "errada-errada"}).status_code == 401
    assert b.post("/api/auth/login", json={"email": "A@Example.com", "password": PASSWORD}).status_code == 200
    assert b.get("/api/auth/me").status_code == 200
    assert b.post("/api/auth/logout").status_code == 204
    assert b.get("/api/auth/me").status_code == 401
    assert a.get("/api/auth/me").status_code == 200  # other sessions survive a logout


def test_unknown_email_and_wrong_password_look_the_same(api):
    api.register("a@example.com")
    r1 = api.post("/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    r2 = api.post("/api/auth/login", json={"email": "a@example.com", "password": "errada-errada"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()


def test_login_rate_limited(new_api):
    new_api().register("a@example.com")
    b = new_api()
    for _ in range(5):
        assert b.post("/api/auth/login", json={"email": "a@example.com", "password": "errada-errada"}).status_code == 401
    r = b.post("/api/auth/login", json={"email": "a@example.com", "password": PASSWORD})
    assert r.status_code == 429


def test_csrf_header_required_for_unsafe_methods(app):
    from fastapi.testclient import TestClient
    raw = TestClient(app)
    r = raw.post("/api/auth/login", json={"email": "a@example.com", "password": PASSWORD})
    assert r.status_code == 403
    assert raw.get("/api/health").status_code == 200


def test_password_reset_flow(new_api, app):
    a = new_api()
    a.register("a@example.com")
    b = new_api()
    r = b.post("/api/auth/password-reset/request", json={"email": "a@example.com"})
    assert r.status_code == 202
    unknown = b.post("/api/auth/password-reset/request", json={"email": "nobody@example.com"})
    assert unknown.status_code == 202 and unknown.json() == r.json()  # no account enumeration
    sent = app.state.mailer.sent
    assert len(sent) == 1 and sent[0]["to"] == "a@example.com"
    token = sent[0]["body"].split("#token=")[1].split()[0]

    new_password = "outra-senha-forte-456"
    assert b.post("/api/auth/password-reset/confirm", json={"token": token, "password": new_password}).status_code == 204
    # Reused token refused; old sessions ended; new password works, old one does not.
    assert b.post("/api/auth/password-reset/confirm", json={"token": token, "password": new_password}).status_code == 400
    assert a.get("/api/auth/me").status_code == 401
    assert b.post("/api/auth/login", json={"email": "a@example.com", "password": PASSWORD}).status_code == 401
    assert b.post("/api/auth/login", json={"email": "a@example.com", "password": new_password}).status_code == 200


def test_signup_can_be_disabled(tmp_path):
    from conftest import Api, make_settings
    from mla_api.db import Base
    from mla_api.main import create_app
    app = create_app(make_settings(tmp_path, allow_signup=False))
    Base.metadata.create_all(app.state.engine)
    r = Api(app).post("/api/auth/register", json={"name": "A", "email": "a@example.com", "password": PASSWORD,
                                                  "organization_name": "X"})
    assert r.status_code == 403


def test_audit_never_contains_secrets(api, app):
    api.register("a@example.com")
    api.post("/api/auth/login", json={"email": "a@example.com", "password": "errada-errada"})
    api.post("/api/auth/password-reset/request", json={"email": "a@example.com"})
    with app.state.sessionmaker() as db:
        dump = repr([(e.action, e.details) for e in db.query(AuditEvent).all()])
    assert PASSWORD not in dump and "errada" not in dump and "token" not in dump.lower()


def test_production_refuses_sqlite_and_insecure_cookie(tmp_path):
    import pytest
    from conftest import make_settings
    with pytest.raises(ValueError):
        make_settings(tmp_path, environment="production", cookie_secure=True)
    with pytest.raises(ValueError):
        make_settings(tmp_path, environment="production", database_url="postgresql+psycopg://x/y",
                      cookie_secure=False)
